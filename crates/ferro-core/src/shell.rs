//! ferro-core: POSIX Shell Grammar, Control Flow Engine, and Builtin Diagnostics.
//! Implements if/then/elif/else/fi, for/in/do/done, while/do/done, case/esac,
//! local variable assignments, parameter expansions ($?, $#, $@, $1..$9, ${VAR:-def}),
//! and the `[` / `test` evaluation applet.

use std::cell::RefCell;
use std::collections::HashMap;
use std::env;
use std::fs;
use std::path::Path;
use std::process::ExitCode;
use std::sync::atomic::{AtomicBool, Ordering};

static LOOP_BREAK: AtomicBool = AtomicBool::new(false);
static LOOP_CONTINUE: AtomicBool = AtomicBool::new(false);

#[derive(Debug, Clone)]
pub struct ShellContext {
    pub local_vars: HashMap<String, String>,
    pub positional_params: Vec<String>,
    pub last_status: i32,
}

impl Default for ShellContext {
    fn default() -> Self {
        Self {
            local_vars: HashMap::new(),
            positional_params: Vec::new(),
            last_status: 0,
        }
    }
}

thread_local! {
    pub static CONTEXT: RefCell<ShellContext> = RefCell::new(ShellContext::default());
}

pub fn get_last_status() -> i32 {
    CONTEXT.with(|ctx| ctx.borrow().last_status)
}

pub fn set_last_status(status: i32) {
    CONTEXT.with(|ctx| ctx.borrow_mut().last_status = status);
}

pub fn set_var(key: &str, val: &str) {
    CONTEXT.with(|ctx| {
        ctx.borrow_mut().local_vars.insert(key.to_string(), val.to_string());
    });
    env::set_var(key, val);
}

pub fn get_var(key: &str) -> Option<String> {
    CONTEXT.with(|ctx| {
        if let Some(val) = ctx.borrow().local_vars.get(key) {
            return Some(val.clone());
        }
        env::var(key).ok()
    })
}

pub fn set_positional(params: Vec<String>) {
    CONTEXT.with(|ctx| {
        ctx.borrow_mut().positional_params = params;
    });
}

pub fn shift_positional(n: usize) {
    CONTEXT.with(|ctx| {
        let mut borrow = ctx.borrow_mut();
        if n >= borrow.positional_params.len() {
            borrow.positional_params.clear();
        } else {
            borrow.positional_params.drain(0..n);
        }
    });
}

pub fn is_exit_success(code: &ExitCode) -> bool {
    let s = format!("{:?}", code);
    s.contains("(0)") || s.contains("SUCCESS")
}

pub fn exit_code_to_i32(code: &ExitCode) -> i32 {
    if is_exit_success(code) {
        0
    } else {
        1
    }
}

// ==============================================================================
// Parameter & Variable Expansion ($?, $#, $@, $1..$9, ${VAR:-default}, $VAR)
// ==============================================================================

pub fn expand_string_vars(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;
    let mut in_single_quotes = false;
    let mut in_double_quotes = false;

    while i < chars.len() {
        let c = chars[i];
        if c == '\'' && !in_double_quotes {
            in_single_quotes = !in_single_quotes;
            out.push(c);
            i += 1;
            continue;
        }
        if c == '"' && !in_single_quotes {
            in_double_quotes = !in_double_quotes;
            out.push(c);
            i += 1;
            continue;
        }

        if !in_single_quotes && c == '$' && i + 1 < chars.len() {
            let next = chars[i + 1];
            if next == '?' {
                out.push_str(&get_last_status().to_string());
                i += 2;
                continue;
            } else if next == '$' {
                out.push_str(&std::process::id().to_string());
                i += 2;
                continue;
            } else if next == '#' {
                let len = CONTEXT.with(|ctx| ctx.borrow().positional_params.len());
                out.push_str(&len.to_string());
                i += 2;
                continue;
            } else if next == '*' || next == '@' {
                let joined = CONTEXT.with(|ctx| ctx.borrow().positional_params.join(" "));
                out.push_str(&joined);
                i += 2;
                continue;
            } else if next.is_ascii_digit() {
                let idx = next.to_digit(10).unwrap() as usize;
                if idx == 0 {
                    out.push_str("ferro-core");
                } else {
                    let val = CONTEXT.with(|ctx| {
                        let borrow = ctx.borrow();
                        borrow.positional_params.get(idx - 1).cloned()
                    });
                    if let Some(v) = val {
                        out.push_str(&v);
                    }
                }
                i += 2;
                continue;
            } else if next == '{' {
                // Bracketed expansion: ${VAR} or ${VAR:-default}
                let mut close_idx = None;
                for j in (i + 2)..chars.len() {
                    if chars[j] == '}' {
                        close_idx = Some(j);
                        break;
                    }
                }
                if let Some(end) = close_idx {
                    let inner: String = chars[(i + 2)..end].iter().collect();
                    if let Some(sep) = inner.find(":-") {
                        let var_name = &inner[..sep];
                        let default_val = &inner[sep + 2..];
                        let val = get_var(var_name);
                        if let Some(v) = val {
                            if !v.is_empty() {
                                out.push_str(&v);
                            } else {
                                out.push_str(default_val);
                            }
                        } else {
                            out.push_str(default_val);
                        }
                    } else {
                        if let Some(v) = get_var(&inner) {
                            out.push_str(&v);
                        }
                    }
                    i = end + 1;
                    continue;
                }
            } else if next.is_ascii_alphabetic() || next == '_' {
                // Simple $VAR
                let mut end = i + 1;
                while end < chars.len() && (chars[end].is_ascii_alphanumeric() || chars[end] == '_') {
                    end += 1;
                }
                let var_name: String = chars[(i + 1)..end].iter().collect();
                if let Some(v) = get_var(&var_name) {
                    out.push_str(&v);
                }
                i = end;
                continue;
            }
        }
        out.push(chars[i]);
        i += 1;
    }

    out
}

pub fn is_assignment(token: &str) -> Option<(String, String)> {
    if let Some(eq_pos) = token.find('=') {
        if eq_pos > 0 {
            let key = &token[..eq_pos];
            let first_char = key.chars().next().unwrap();
            if (first_char.is_ascii_alphabetic() || first_char == '_')
                && key.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
            {
                let raw_val = &token[eq_pos + 1..];
                let clean_val = raw_val
                    .trim_matches(|c| c == '"' || c == '\'')
                    .to_string();
                return Some((key.to_string(), expand_string_vars(&clean_val)));
            }
        }
    }
    None
}

// ==============================================================================
// Builtin `[` and `test` Expression Evaluator
// ==============================================================================

pub fn run_test(args: &[String]) -> ExitCode {
    let mut tokens: Vec<String> = args.to_vec();

    // If invoked as `[`, remove optional trailing `]`
    if let Some(last) = tokens.last() {
        if last == "]" {
            tokens.pop();
        }
    }

    if tokens.is_empty() {
        return ExitCode::FAILURE;
    }

    // Handle logical negation `!`
    let mut invert = false;
    if tokens[0] == "!" {
        invert = true;
        tokens.remove(0);
    }

    if tokens.is_empty() {
        return if invert { ExitCode::SUCCESS } else { ExitCode::FAILURE };
    }

    let result = evaluate_test_expr(&tokens);
    let final_res = if invert { !result } else { result };

    if final_res {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

fn evaluate_test_expr(tokens: &[String]) -> bool {
    match tokens.len() {
        1 => {
            // Non-empty string is true
            !tokens[0].is_empty()
        }
        2 => {
            let op = tokens[0].as_str();
            let arg = &tokens[1];
            let p = Path::new(arg);
            match op {
                "-f" => p.is_file(),
                "-d" => p.is_dir(),
                "-e" => p.exists(),
                "-s" => fs::metadata(p).map(|m| m.len() > 0).unwrap_or(false),
                "-r" => {
                    #[cfg(unix)]
                    {
                        use std::ffi::CString;
                        CString::new(arg.as_str()).map(|c| unsafe { libc::access(c.as_ptr(), libc::R_OK) == 0 }).unwrap_or(false)
                    }
                    #[cfg(not(unix))]
                    p.exists()
                }
                "-w" => {
                    #[cfg(unix)]
                    {
                        use std::ffi::CString;
                        CString::new(arg.as_str()).map(|c| unsafe { libc::access(c.as_ptr(), libc::W_OK) == 0 }).unwrap_or(false)
                    }
                    #[cfg(not(unix))]
                    p.exists()
                }
                "-x" => {
                    #[cfg(unix)]
                    {
                        use std::ffi::CString;
                        CString::new(arg.as_str()).map(|c| unsafe { libc::access(c.as_ptr(), libc::X_OK) == 0 }).unwrap_or(false)
                    }
                    #[cfg(not(unix))]
                    p.exists()
                }
                "-L" | "-h" => fs::symlink_metadata(p)
                    .map(|m| m.file_type().is_symlink())
                    .unwrap_or(false),
                "-z" => arg.is_empty(),
                "-n" => !arg.is_empty(),
                _ => false,
            }
        }
        3 => {
            let left = &tokens[0];
            let op = tokens[1].as_str();
            let right = &tokens[2];

            match op {
                "=" | "==" => left == right,
                "!=" => left != right,
                "-eq" => {
                    let l = left.parse::<i64>().unwrap_or(i64::MIN);
                    let r = right.parse::<i64>().unwrap_or(i64::MAX);
                    l == r
                }
                "-ne" => {
                    let l = left.parse::<i64>().unwrap_or(i64::MIN);
                    let r = right.parse::<i64>().unwrap_or(i64::MAX);
                    l != r
                }
                "-lt" => {
                    let l = left.parse::<i64>().unwrap_or(0);
                    let r = right.parse::<i64>().unwrap_or(0);
                    l < r
                }
                "-gt" => {
                    let l = left.parse::<i64>().unwrap_or(0);
                    let r = right.parse::<i64>().unwrap_or(0);
                    l > r
                }
                "-le" => {
                    let l = left.parse::<i64>().unwrap_or(0);
                    let r = right.parse::<i64>().unwrap_or(0);
                    l <= r
                }
                "-ge" => {
                    let l = left.parse::<i64>().unwrap_or(0);
                    let r = right.parse::<i64>().unwrap_or(0);
                    l >= r
                }
                _ => false,
            }
        }
        _ => {
            // Complex expression: check if wrapped in parentheses or contains binary connectives
            if tokens[0] == "-f" {
                Path::new(&tokens[1]).is_file()
            } else if tokens[0] == "-d" {
                Path::new(&tokens[1]).is_dir()
            } else if tokens[0] == "-e" {
                Path::new(&tokens[1]).exists()
            } else {
                !tokens.join(" ").trim().is_empty()
            }
        }
    }
}

// ==============================================================================
// Statement Tokenizer (Handles quotes, semicolons, and newlines)
// ==============================================================================

pub fn split_statements(script: &str) -> Vec<String> {
    let mut stmts = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    let mut quote_char = ' ';
    let mut in_comment = false;

    for c in script.chars() {
        if in_comment {
            if c == '\n' {
                in_comment = false;
                let trimmed = current.trim();
                if !trimmed.is_empty() && !trimmed.starts_with('#') {
                    stmts.push(trimmed.to_string());
                }
                current.clear();
            }
            continue;
        }

        match c {
            '"' | '\'' if !in_quotes => {
                in_quotes = true;
                quote_char = c;
                current.push(c);
            }
            c if in_quotes && c == quote_char => {
                in_quotes = false;
                current.push(c);
            }
            '#' if !in_quotes && (current.trim().is_empty() || current.ends_with(char::is_whitespace)) => {
                in_comment = true;
            }
            ';' | '\n' if !in_quotes => {
                let trimmed = current.trim();
                if !trimmed.is_empty() && !trimmed.starts_with('#') {
                    stmts.push(trimmed.to_string());
                }
                current.clear();
            }
            _ => {
                current.push(c);
            }
        }
    }
    let trimmed = current.trim();
    if !trimmed.is_empty() && !trimmed.starts_with('#') {
        stmts.push(trimmed.to_string());
    }
    stmts
}

// ==============================================================================
// Control Flow Parser & Execution Engine
// ==============================================================================

pub fn execute_script<F>(script: &str, exec_pipeline: F) -> ExitCode
where
    F: FnMut(&str) -> ExitCode + Copy,
{
    let stmts = split_statements(script);
    let mut i = 0;
    let mut last_code = ExitCode::SUCCESS;

    while i < stmts.len() {
        let stmt = stmts[i].trim();
        if stmt.is_empty() || stmt.starts_with('#') {
            i += 1;
            continue;
        }

        if LOOP_BREAK.load(Ordering::SeqCst) || LOOP_CONTINUE.load(Ordering::SeqCst) {
            break;
        }

        if stmt == "break" || stmt.starts_with("break ") || stmt.starts_with("break;") {
            LOOP_BREAK.store(true, Ordering::SeqCst);
            last_code = ExitCode::SUCCESS;
            set_last_status(0);
            break;
        } else if stmt == "continue" || stmt.starts_with("continue ") || stmt.starts_with("continue;") {
            LOOP_CONTINUE.store(true, Ordering::SeqCst);
            last_code = ExitCode::SUCCESS;
            set_last_status(0);
            break;
        }

        // 1. `if` block parsing
        if stmt.starts_with("if ") || stmt == "if" {
            let (cond, then_body, elifs, else_body, next_idx) = parse_if_block(&stmts, i);
            i = next_idx;

            let cond_code = execute_script(&cond, exec_pipeline);
            if is_exit_success(&cond_code) {
                last_code = execute_script(&then_body, exec_pipeline);
            } else {
                let mut matched = false;
                for (elif_cond, elif_body) in elifs {
                    let elif_res = execute_script(&elif_cond, exec_pipeline);
                    if is_exit_success(&elif_res) {
                        last_code = execute_script(&elif_body, exec_pipeline);
                        matched = true;
                        break;
                    }
                }
                if !matched {
                    if let Some(else_b) = else_body {
                        last_code = execute_script(&else_b, exec_pipeline);
                    }
                }
            }
            set_last_status(exit_code_to_i32(&last_code));
            continue;
        }

        // 2. `for` loop parsing
        if stmt.starts_with("for ") {
            let (var_name, items, body, next_idx) = parse_for_block(&stmts, i);
            i = next_idx;

            for item in items {
                set_var(&var_name, &item);
                last_code = execute_script(&body, exec_pipeline);
                if LOOP_BREAK.swap(false, Ordering::SeqCst) {
                    break;
                }
                if LOOP_CONTINUE.swap(false, Ordering::SeqCst) {
                    continue;
                }
            }
            set_last_status(exit_code_to_i32(&last_code));
            continue;
        }

        // 3. `while` loop parsing
        if stmt.starts_with("while ") {
            let (cond, body, next_idx) = parse_while_block(&stmts, i);
            i = next_idx;

            let mut loop_count = 0;
            while loop_count < 100_000 {
                // Safeguard against infinite loops
                let cond_res = execute_script(&cond, exec_pipeline);
                if !is_exit_success(&cond_res) {
                    break;
                }
                last_code = execute_script(&body, exec_pipeline);
                if LOOP_BREAK.swap(false, Ordering::SeqCst) {
                    break;
                }
                if LOOP_CONTINUE.swap(false, Ordering::SeqCst) {
                    continue;
                }
                loop_count += 1;
            }
            set_last_status(exit_code_to_i32(&last_code));
            continue;
        }

        // 4. `case` block parsing
        if stmt.starts_with("case ") {
            let (target_word, arms, next_idx) = parse_case_block(&stmts, i);
            i = next_idx;

            let expanded_word = expand_string_vars(&target_word)
                .trim()
                .trim_matches(|c| c == '"' || c == '\'')
                .to_string();
            for (pattern, body) in arms {
                let clean_pattern = pattern.trim().trim_matches(|c| c == '"' || c == '\'');
                if pattern_matches(clean_pattern, &expanded_word) {
                    last_code = execute_script(&body, exec_pipeline);
                    break;
                }
            }
            set_last_status(exit_code_to_i32(&last_code));
            continue;
        }

        // 5. Variable Assignment (e.g. VAR=val or export VAR=val)
        let expanded_stmt = expand_string_vars(stmt);
        if let Some((k, v)) = is_assignment(stmt) {
            set_var(&k, &v);
            last_code = ExitCode::SUCCESS;
            set_last_status(0);
            i += 1;
            continue;
        } else if stmt.starts_with("export ") {
            let rest = stmt.trim_start_matches("export ").trim();
            if let Some((k, v)) = is_assignment(rest) {
                set_var(&k, &v);
            } else if !rest.is_empty() {
                if let Some(existing) = get_var(rest) {
                    env::set_var(rest, existing);
                }
            }
            last_code = ExitCode::SUCCESS;
            set_last_status(0);
            i += 1;
            continue;
        } else if stmt.starts_with("shift") {
            let parts: Vec<&str> = stmt.split_whitespace().collect();
            let n = parts
                .get(1)
                .and_then(|s| s.parse::<usize>().ok())
                .unwrap_or(1);
            shift_positional(n);
            last_code = ExitCode::SUCCESS;
            set_last_status(0);
            i += 1;
            continue;
        }

        // 6. Pipeline execution with `||` and `&&` chaining
        last_code = execute_logical_chain(&expanded_stmt, exec_pipeline);
        set_last_status(exit_code_to_i32(&last_code));
        i += 1;
    }

    last_code
}

fn split_logical_chain(stmt: &str) -> Vec<(Option<&str>, String)> {
    let mut parts = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    let mut quote_char = ' ';
    let chars: Vec<char> = stmt.chars().collect();
    let mut i = 0;
    let mut last_op: Option<&'static str> = None;

    while i < chars.len() {
        let c = chars[i];
        if (c == '"' || c == '\'') && !in_quotes {
            in_quotes = true;
            quote_char = c;
            current.push(c);
            i += 1;
        } else if in_quotes && c == quote_char {
            in_quotes = false;
            current.push(c);
            i += 1;
        } else if !in_quotes && i + 1 < chars.len() && ((c == '&' && chars[i + 1] == '&') || (c == '|' && chars[i + 1] == '|')) {
            let op = if c == '&' { "&&" } else { "||" };
            let sub = current.trim().to_string();
            if !sub.is_empty() {
                parts.push((last_op, sub));
            }
            current.clear();
            last_op = Some(op);
            i += 2;
        } else {
            current.push(c);
            i += 1;
        }
    }
    let sub = current.trim().to_string();
    if !sub.is_empty() {
        parts.push((last_op, sub));
    }
    parts
}

fn execute_logical_chain<F>(stmt: &str, mut exec_pipeline: F) -> ExitCode
where
    F: FnMut(&str) -> ExitCode,
{
    let chain = split_logical_chain(stmt);
    if chain.is_empty() {
        return ExitCode::SUCCESS;
    }

    let mut last_code = ExitCode::SUCCESS;

    for (op, subcmd) in chain {
        let should_run = match op {
            None => true,
            Some("&&") => is_exit_success(&last_code),
            Some("||") => !is_exit_success(&last_code),
            _ => true,
        };

        if should_run {
            last_code = exec_pipeline(&subcmd);
        }
    }

    last_code
}

// -------------------------------------------------------------
// Control Flow Block Parsers
// -------------------------------------------------------------

fn parse_if_block(
    stmts: &[String],
    start: usize,
) -> (String, String, Vec<(String, String)>, Option<String>, usize) {
    let mut cond = String::new();
    let mut then_body = Vec::new();
    let mut elifs = Vec::new();
    let mut else_body = Vec::new();

    let mut current_elif_cond = String::new();
    let mut current_elif_body = Vec::new();

    enum Section {
        Cond,
        Then,
        ElifCond,
        ElifBody,
        Else,
    }
    let mut section = Section::Cond;
    let mut depth = 0;
    let mut idx = start;

    while idx < stmts.len() {
        let line = stmts[idx].trim();

        if (line.starts_with("if ") || line == "if") && idx > start {
            depth += 1;
        }

        if depth == 0 {
            if line.starts_with("if ") {
                let rest = line.trim_start_matches("if ").trim();
                if let Some(then_pos) = rest.find("then") {
                    cond = rest[..then_pos].trim().to_string();
                    let rem = rest[then_pos + 4..].trim();
                    if !rem.is_empty() {
                        then_body.push(rem.to_string());
                    }
                    section = Section::Then;
                } else {
                    cond = rest.to_string();
                }
                idx += 1;
                continue;
            } else if line == "then" && matches!(section, Section::Cond) {
                section = Section::Then;
                idx += 1;
                continue;
            } else if line.starts_with("then ") && matches!(section, Section::Cond) {
                section = Section::Then;
                then_body.push(line.trim_start_matches("then ").trim().to_string());
                idx += 1;
                continue;
            } else if line.starts_with("elif ") {
                if matches!(section, Section::ElifBody) {
                    elifs.push((current_elif_cond.clone(), current_elif_body.join("; ")));
                    current_elif_body.clear();
                }
                let rest = line.trim_start_matches("elif ").trim();
                if let Some(then_pos) = rest.find("then") {
                    current_elif_cond = rest[..then_pos].trim().to_string();
                    let rem = rest[then_pos + 4..].trim();
                    if !rem.is_empty() {
                        current_elif_body.push(rem.to_string());
                    }
                    section = Section::ElifBody;
                } else {
                    current_elif_cond = rest.to_string();
                    section = Section::ElifCond;
                }
                idx += 1;
                continue;
            } else if line == "then" && matches!(section, Section::ElifCond) {
                section = Section::ElifBody;
                idx += 1;
                continue;
            } else if line == "else" {
                if matches!(section, Section::ElifBody) {
                    elifs.push((current_elif_cond.clone(), current_elif_body.join("; ")));
                    current_elif_body.clear();
                }
                section = Section::Else;
                idx += 1;
                continue;
            } else if line == "fi" || line.starts_with("fi ") || line.starts_with("fi&") || line.starts_with("fi;") {
                if matches!(section, Section::ElifBody) {
                    elifs.push((current_elif_cond.clone(), current_elif_body.join("; ")));
                }
                idx += 1;
                break;
            }
        }

        if line == "fi" && depth > 0 {
            depth -= 1;
        }

        match section {
            Section::Cond => cond.push_str(&format!(" {}; ", line)),
            Section::Then => then_body.push(line.to_string()),
            Section::ElifCond => current_elif_cond.push_str(&format!(" {}; ", line)),
            Section::ElifBody => current_elif_body.push(line.to_string()),
            Section::Else => else_body.push(line.to_string()),
        }

        idx += 1;
    }

    let else_opt = if else_body.is_empty() {
        None
    } else {
        Some(else_body.join("; "))
    };

    (cond, then_body.join("; "), elifs, else_opt, idx)
}

fn parse_for_block(stmts: &[String], start: usize) -> (String, Vec<String>, String, usize) {
    let first = &stmts[start];
    let rest = first.trim_start_matches("for ").trim();

    let (var_name, raw_items) = if let Some(in_pos) = rest.find(" in ") {
        let name = rest[..in_pos].trim().to_string();
        let items_part = rest[in_pos + 4..].trim();
        let items: Vec<String> = if let Some(do_pos) = items_part.find("; do") {
            items_part[..do_pos].split_whitespace().map(String::from).collect()
        } else if let Some(do_pos) = items_part.find(" do") {
            items_part[..do_pos].split_whitespace().map(String::from).collect()
        } else {
            items_part.split_whitespace().map(String::from).collect()
        };
        (name, items)
    } else {
        // POSIX shorthand: `for var do` or `for var; do` defaults to iterating over "$@"
        let name_part = if let Some(do_pos) = rest.find(" do") {
            &rest[..do_pos]
        } else if let Some(semi_pos) = rest.find(';') {
            &rest[..semi_pos]
        } else {
            rest
        };
        (name_part.trim().to_string(), vec!["$@".to_string()])
    };
    let mut body = Vec::new();

    let mut depth = 0;
    let mut idx = start + 1;
    let mut in_body = first.contains(" do");

    while idx < stmts.len() {
        let line = stmts[idx].trim();
        if line.starts_with("for ") || line.starts_with("while ") {
            depth += 1;
        }

        if depth == 0 {
            if line == "do" {
                in_body = true;
                idx += 1;
                continue;
            } else if line.starts_with("do ") {
                in_body = true;
                body.push(line.trim_start_matches("do ").trim().to_string());
                idx += 1;
                continue;
            } else if line == "done" {
                idx += 1;
                break;
            } else if line.starts_with("done ") || line.starts_with("done&") || line.starts_with("done;") {
                idx += 1;
                break;
            }
        }

        if (line == "done" || line.starts_with("done ") || line.starts_with("done&")) && depth > 0 {
            depth -= 1;
        }

        if in_body {
            body.push(line.to_string());
        }
        idx += 1;
    }

    // Expand items (e.g. "$@")
    let mut expanded_items = Vec::new();
    for it in raw_items {
        let expanded = expand_string_vars(&it);
        for word in expanded.split_whitespace() {
            expanded_items.push(word.to_string());
        }
    }

    (var_name, expanded_items, body.join("; "), idx)
}

fn parse_while_block(stmts: &[String], start: usize) -> (String, String, usize) {
    let first = &stmts[start];
    let mut cond = first.trim_start_matches("while ").trim().to_string();
    let mut body = Vec::new();

    let mut depth = 0;
    let mut idx = start + 1;
    let mut in_body = false;

    if let Some(do_pos) = cond.find(" do") {
        cond = cond[..do_pos].trim().to_string();
        in_body = true;
    }

    while idx < stmts.len() {
        let line = stmts[idx].trim();
        if line.starts_with("while ") || line.starts_with("for ") {
            depth += 1;
        }

        if depth == 0 {
            if line == "do" {
                in_body = true;
                idx += 1;
                continue;
            } else if line.starts_with("do ") {
                in_body = true;
                body.push(line.trim_start_matches("do ").trim().to_string());
                idx += 1;
                continue;
            } else if line == "done" {
                idx += 1;
                break;
            } else if line.starts_with("done ") || line.starts_with("done&") || line.starts_with("done;") {
                idx += 1;
                break;
            }
        }

        if (line == "done" || line.starts_with("done ") || line.starts_with("done&")) && depth > 0 {
            depth -= 1;
        }

        if in_body {
            body.push(line.to_string());
        } else {
            cond.push_str(&format!(" {}; ", line));
        }
        idx += 1;
    }

    (cond, body.join("; "), idx)
}

fn parse_case_block(stmts: &[String], start: usize) -> (String, Vec<(String, String)>, usize) {
    let first = &stmts[start];
    let rest = first.trim_start_matches("case ").trim();
    let word = rest.trim_end_matches(" in").trim().to_string();

    let mut arms = Vec::new();
    let mut current_pattern = String::new();
    let mut current_body = Vec::new();
    let mut idx = start + 1;

    while idx < stmts.len() {
        let line = stmts[idx].trim();
        if line == "esac" {
            if !current_pattern.is_empty() {
                arms.push((current_pattern.clone(), current_body.join("; ")));
            }
            idx += 1;
            break;
        }

        if let Some(paren_pos) = line.find(')') {
            // Pattern found before `)`
            if !current_pattern.is_empty() {
                arms.push((current_pattern.clone(), current_body.join("; ")));
                current_body.clear();
            }
            current_pattern = line[..paren_pos].trim().to_string();
            let after_paren = line[paren_pos + 1..].trim();

            if after_paren.ends_with(";;") {
                let clean = after_paren.trim_end_matches(";;").trim();
                if !clean.is_empty() {
                    current_body.push(clean.to_string());
                }
                arms.push((current_pattern.clone(), current_body.join("; ")));
                current_pattern.clear();
                current_body.clear();
            } else if !after_paren.is_empty() {
                current_body.push(after_paren.to_string());
            }
            idx += 1;
            continue;
        } else if line.ends_with(";;") {
            let clean = line.trim_end_matches(";;").trim();
            if !clean.is_empty() {
                current_body.push(clean.to_string());
            }
            if !current_pattern.is_empty() {
                arms.push((current_pattern.clone(), current_body.join("; ")));
                current_pattern.clear();
                current_body.clear();
            }
            idx += 1;
            continue;
        }

        current_body.push(line.to_string());
        idx += 1;
    }

    (word, arms, idx)
}

fn pattern_matches(pattern: &str, text: &str) -> bool {
    let pats: Vec<&str> = pattern.split('|').map(|s| s.trim()).collect();
    for p in pats {
        if p == "*" || p == text {
            return true;
        }
        if p.starts_with('*') && text.ends_with(&p[1..]) {
            return true;
        }
        if p.ends_with('*') && text.starts_with(&p[..p.len() - 1]) {
            return true;
        }
    }
    false
}

// ==============================================================================
// Unit Tests for Shell Control Flow & Expressions
// ==============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_variable_expansion_and_assignment() {
        set_var("FERRO_TEST_KEY", "ferro_value");
        assert_eq!(get_var("FERRO_TEST_KEY").unwrap(), "ferro_value");

        set_last_status(42);
        assert_eq!(expand_string_vars("Status is $?"), "Status is 42");

        let expanded = expand_string_vars("Path: ${FERRO_TEST_KEY}/bin");
        assert_eq!(expanded, "Path: ferro_value/bin");

        let with_default = expand_string_vars("${NONEXISTENT_VAR:-fallback_123}");
        assert_eq!(with_default, "fallback_123");
    }

    #[test]
    fn test_builtin_test_evaluation() {
        // String checks
        assert!(is_exit_success(&run_test(&["hello".into()])));
        assert!(is_exit_success(&run_test(&["-z".into(), "".into()])));
        assert!(is_exit_success(&run_test(&["-n".into(), "abc".into()])));
        assert!(!is_exit_success(&run_test(&["-n".into(), "".into()])));

        // Comparisons
        assert!(is_exit_success(&run_test(&[
            "apple".into(),
            "=".into(),
            "apple".into()
        ])));
        assert!(is_exit_success(&run_test(&[
            "apple".into(),
            "!=".into(),
            "banana".into()
        ])));
        assert!(is_exit_success(&run_test(&[
            "10".into(),
            "-eq".into(),
            "10".into()
        ])));
        assert!(is_exit_success(&run_test(&[
            "5".into(),
            "-lt".into(),
            "10".into()
        ])));
        assert!(is_exit_success(&run_test(&[
            "15".into(),
            "-gt".into(),
            "10".into()
        ])));

        // Logical NOT `!`
        assert!(is_exit_success(&run_test(&[
            "!".into(),
            "apple".into(),
            "=".into(),
            "banana".into()
        ])));

        // Bracket syntax `[ ... ]`
        assert!(is_exit_success(&run_test(&[
            "10".into(),
            "-eq".into(),
            "10".into(),
            "]".into()
        ])));
    }

    #[test]
    fn test_script_control_flow_execution() {
        let script = r#"
        X=100
        if [ "$X" -eq 100 ]; then
            Y=passed
        else
            Y=failed
        fi
        "#;

        let code = execute_script(script, |stmt| {
            if stmt.starts_with("Y=") {
                let v = stmt.trim_start_matches("Y=");
                set_var("Y", v);
            }
            ExitCode::SUCCESS
        });

        assert!(is_exit_success(&code));
        assert_eq!(get_var("Y").unwrap(), "passed");
    }

    #[test]
    fn test_for_loop_execution() {
        let script = r#"
        for item in a b c; do
            LAST_ITEM=$item
        done
        "#;

        let code = execute_script(script, |stmt| {
            if stmt.starts_with("LAST_ITEM=") {
                let v = stmt.trim_start_matches("LAST_ITEM=");
                set_var("LAST_ITEM", v);
            }
            ExitCode::SUCCESS
        });

        assert!(is_exit_success(&code));
        assert_eq!(get_var("LAST_ITEM").unwrap(), "c");
    }

    #[test]
    fn test_case_statement_execution() {
        let script = r#"
        TARGET=prod
        case "$TARGET" in
            dev)
                ENV_TYPE=development
                ;;
            prod|production)
                ENV_TYPE=production
                ;;
            *)
                ENV_TYPE=unknown
                ;;
        esac
        "#;

        let code = execute_script(script, |stmt| {
            if stmt.starts_with("ENV_TYPE=") {
                let v = stmt.trim_start_matches("ENV_TYPE=");
                set_var("ENV_TYPE", v);
            }
            ExitCode::SUCCESS
        });

        assert!(is_exit_success(&code));
        assert_eq!(get_var("ENV_TYPE").unwrap(), "production");
    }
}
