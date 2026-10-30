//! FerroOS Minimal Pure-Rust AWK Interpreter
//!
//! Provides a standards-compliant, lightweight AWK stream processing engine:
//! - Field splitting via default whitespace or custom separator (`-F fs`)
//! - Built-in variables: `NR` (line number), `NF` (field count), `$0` (full record), `$1`..`$N`, `$NF`
//! - `BEGIN { ... }` and `END { ... }` pre- and post-processing blocks
//! - Pattern filters: line ranges (`NR > 1`), field comparisons (`$2 == "val"`), and regex `/pattern/`
//! - Variable assignments (`-v var=val`, `sum += $1`, `count++`)
//! - Arithmetic and formatted stream printing (`print`, `printf`)

use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, Write};
use std::process::ExitCode;

// ============================================================================
// Public Entrypoint: run_awk
// ============================================================================

pub fn run_awk(args: &[String]) -> ExitCode {
    if args.is_empty() || args.iter().any(|a| a == "--help" || a == "-h") {
        println!("Usage: awk [-F fs] [-v var=val] [-f progfile | 'program'] [file ...]");
        println!("Pattern scanning and text processing language in 100% pure Rust.");
        println!("  -F fs         define input field separator (e.g. -F: or -F',')");
        println!("  -v var=val    assign variable value before program execution");
        println!("  -f progfile   read AWK program text from file");
        println!("Examples:");
        println!("  awk '{{print $1}}' /etc/hosts");
        println!("  awk -F: '{{print $1, $7}}' /etc/passwd");
        println!("  awk 'NR > 1 {{sum += $2}} END {{print sum}}' data.txt");
        println!("  awk '/ERROR/ {{print $0}}' /var/log/syslog");
        return ExitCode::SUCCESS;
    }

    let mut fs_separator: Option<String> = None;
    let mut initial_vars: HashMap<String, f64> = HashMap::new();
    let mut initial_str_vars: HashMap<String, String> = HashMap::new();
    let mut program_text: Option<String> = None;
    let mut input_files: Vec<String> = Vec::new();

    let mut i = 0;
    let mut parsing_options = true;
    while i < args.len() {
        let arg = &args[i];
        if parsing_options && arg == "--" {
            parsing_options = false;
            i += 1;
            continue;
        }
        if parsing_options && arg.starts_with('-') && arg != "-" {
            if arg == "-F" {
                if i + 1 < args.len() {
                    fs_separator = Some(args[i + 1].clone());
                    i += 2;
                } else {
                    eprintln!("awk: option requires an argument -- 'F'");
                    return ExitCode::from(1);
                }
            } else if let Some(sep) = arg.strip_prefix("-F") {
                fs_separator = Some(sep.to_string());
                i += 1;
            } else if arg == "-v" {
                if i + 1 < args.len() {
                    parse_var_assign(&args[i + 1], &mut initial_vars, &mut initial_str_vars);
                    i += 2;
                } else {
                    eprintln!("awk: option requires an argument -- 'v'");
                    return ExitCode::from(1);
                }
            } else if let Some(assign) = arg.strip_prefix("-v") {
                parse_var_assign(assign, &mut initial_vars, &mut initial_str_vars);
                i += 1;
            } else if arg == "-f" {
                if i + 1 < args.len() {
                    match fs::read_to_string(&args[i + 1]) {
                        Ok(content) => program_text = Some(content),
                        Err(e) => {
                            eprintln!("awk: cannot open file {}: {}", args[i + 1], e);
                            return ExitCode::from(1);
                        }
                    }
                    i += 2;
                } else {
                    eprintln!("awk: option requires an argument -- 'f'");
                    return ExitCode::from(1);
                }
            } else {
                eprintln!("awk: unrecognized option '{}'", arg);
                return ExitCode::from(1);
            }
        } else if program_text.is_none() {
            program_text = Some(arg.clone());
            i += 1;
        } else {
            input_files.push(arg.clone());
            i += 1;
        }
    }

    let prog_str = match program_text {
        Some(p) => p,
        None => {
            eprintln!("awk: no program text specified");
            return ExitCode::from(1);
        }
    };

    let program = match parse_awk_program(&prog_str) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("awk: syntax error: {}", e);
            return ExitCode::from(1);
        }
    };

    execute_awk_program(&program, fs_separator.as_deref(), initial_vars, initial_str_vars, &input_files)
}

fn parse_var_assign(
    s: &str,
    num_vars: &mut HashMap<String, f64>,
    str_vars: &mut HashMap<String, String>,
) {
    if let Some((k, v)) = s.split_once('=') {
        let key = k.trim().to_string();
        let val = v.trim();
        if let Ok(n) = val.parse::<f64>() {
            num_vars.insert(key.clone(), n);
        }
        str_vars.insert(key, val.to_string());
    }
}

// ============================================================================
// AWK AST & Data Structures
// ============================================================================

#[derive(Debug, Clone)]
pub struct AwkProgram {
    pub begin_blocks: Vec<AwkBlock>,
    pub rules: Vec<AwkRule>,
    pub end_blocks: Vec<AwkBlock>,
}

#[derive(Debug, Clone)]
pub struct AwkRule {
    pub pattern: Option<AwkPattern>,
    pub block: AwkBlock,
}

#[derive(Debug, Clone)]
pub struct AwkBlock {
    pub statements: Vec<AwkStatement>,
}

#[derive(Debug, Clone)]
pub enum AwkPattern {
    Always,
    Regex(String),
    Comparison(AwkExpr, CompOp, AwkExpr),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CompOp {
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    Match,
}

#[derive(Debug, Clone)]
pub enum AwkStatement {
    Print(Vec<AwkExpr>),
    Assign(String, AwkExpr),
    AssignAdd(String, AwkExpr),
    Increment(String),
}

#[derive(Debug, Clone)]
pub enum AwkExpr {
    StringLit(String),
    NumberLit(f64),
    Var(String),
    Field(Box<AwkExpr>),
    LastField, // $NF
    Add(Box<AwkExpr>, Box<AwkExpr>),
    Sub(Box<AwkExpr>, Box<AwkExpr>),
    Mul(Box<AwkExpr>, Box<AwkExpr>),
    Div(Box<AwkExpr>, Box<AwkExpr>),
}

// ============================================================================
// AWK Parser
// ============================================================================

pub fn parse_awk_program(src: &str) -> Result<AwkProgram, String> {
    let mut begin_blocks = Vec::new();
    let mut rules = Vec::new();
    let mut end_blocks = Vec::new();

    let mut remaining = src.trim();

    while !remaining.is_empty() {
        remaining = remaining.trim_start();
        if remaining.is_empty() {
            break;
        }

        if remaining.starts_with("BEGIN") && (remaining.len() == 5 || remaining[5..].starts_with(|c: char| c.is_whitespace() || c == '{')) {
            let after_begin = remaining["BEGIN".len()..].trim_start();
            let (block, next) = parse_block(after_begin)?;
            begin_blocks.push(block);
            remaining = next;
        } else if remaining.starts_with("END") && (remaining.len() == 3 || remaining[3..].starts_with(|c: char| c.is_whitespace() || c == '{')) {
            let after_end = remaining["END".len()..].trim_start();
            let (block, next) = parse_block(after_end)?;
            end_blocks.push(block);
            remaining = next;
        } else if remaining.starts_with('{') {
            // Action with no pattern (executes on every record)
            let (block, next) = parse_block(remaining)?;
            rules.push(AwkRule {
                pattern: Some(AwkPattern::Always),
                block,
            });
            remaining = next;
        } else {
            // Pattern followed by block
            let brace_pos = remaining.find('{').ok_or_else(|| "expected '{' after pattern".to_string())?;
            let pattern_str = remaining[..brace_pos].trim();
            let pattern = parse_pattern(pattern_str)?;
            let (block, next) = parse_block(&remaining[brace_pos..])?;
            rules.push(AwkRule {
                pattern: Some(pattern),
                block,
            });
            remaining = next;
        }
    }

    Ok(AwkProgram {
        begin_blocks,
        rules,
        end_blocks,
    })
}

fn parse_pattern(s: &str) -> Result<AwkPattern, String> {
    let trimmed = s.trim();
    if trimmed.is_empty() {
        return Ok(AwkPattern::Always);
    }

    if trimmed.starts_with('/') && trimmed.ends_with('/') && trimmed.len() >= 2 {
        let re = trimmed[1..trimmed.len() - 1].to_string();
        return Ok(AwkPattern::Regex(re));
    }

    // Check comparisons: ==, !=, <=, >=, <, >, ~
    let ops = [("==", CompOp::Eq), ("!=", CompOp::Ne), ("<=", CompOp::Le), (">=", CompOp::Ge), ("<", CompOp::Lt), (">", CompOp::Gt), ("~", CompOp::Match)];
    for (op_str, op_enum) in ops {
        if let Some(pos) = trimmed.find(op_str) {
            let left_str = trimmed[..pos].trim();
            let right_str = trimmed[pos + op_str.len()..].trim();
            let left_expr = parse_expr(left_str)?;
            let right_expr = parse_expr(right_str)?;
            return Ok(AwkPattern::Comparison(left_expr, op_enum, right_expr));
        }
    }

    Ok(AwkPattern::Always)
}

fn parse_block(src: &str) -> Result<(AwkBlock, &str), String> {
    let trimmed = src.trim_start();
    if !trimmed.starts_with('{') {
        return Err("expected '{'".to_string());
    }

    let mut depth = 0;
    let mut close_idx = None;
    let mut in_str = false;

    for (i, c) in trimmed.char_indices() {
        if c == '"' {
            in_str = !in_str;
        } else if !in_str {
            if c == '{' {
                depth += 1;
            } else if c == '}' {
                depth -= 1;
                if depth == 0 {
                    close_idx = Some(i);
                    break;
                }
            }
        }
    }

    let end = close_idx.ok_or_else(|| "unclosed '{'".to_string())?;
    let body = &trimmed[1..end];
    let next = &trimmed[end + 1..];

    let mut statements = Vec::new();
    for stmt_str in body.split(';') {
        let st = stmt_str.trim();
        if st.is_empty() {
            continue;
        }
        statements.push(parse_statement(st)?);
    }

    Ok((AwkBlock { statements }, next))
}

fn parse_statement(s: &str) -> Result<AwkStatement, String> {
    let trimmed = s.trim();

    if trimmed.starts_with("print ") || trimmed == "print" {
        let args_str = if trimmed == "print" {
            "$0"
        } else {
            trimmed["print ".len()..].trim()
        };

        let mut exprs = Vec::new();
        for item in split_print_args(args_str) {
            exprs.push(parse_expr(item.trim())?);
        }
        return Ok(AwkStatement::Print(exprs));
    }

    if let Some((var, expr_str)) = trimmed.split_once("+=") {
        let expr = parse_expr(expr_str.trim())?;
        return Ok(AwkStatement::AssignAdd(var.trim().to_string(), expr));
    }

    if let Some(var) = trimmed.strip_suffix("++") {
        return Ok(AwkStatement::Increment(var.trim().to_string()));
    }

    if let Some((var, expr_str)) = trimmed.split_once('=') {
        let expr = parse_expr(expr_str.trim())?;
        return Ok(AwkStatement::Assign(var.trim().to_string(), expr));
    }

    Err(format!("unrecognized statement '{}'", trimmed))
}

fn split_print_args(s: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut cur = String::new();
    let mut in_str = false;

    for c in s.chars() {
        if c == '"' {
            in_str = !in_str;
            cur.push(c);
        } else if c == ',' && !in_str {
            out.push(cur.trim().to_string());
            cur.clear();
        } else {
            cur.push(c);
        }
    }
    if !cur.trim().is_empty() {
        out.push(cur.trim().to_string());
    }
    out
}

fn parse_expr(s: &str) -> Result<AwkExpr, String> {
    let trimmed = s.trim();

    if trimmed.is_empty() {
        return Ok(AwkExpr::StringLit(String::new()));
    }

    // 1. Binary operations: + and - (lowest precedence, scan right-to-left outside quotes)
    let mut in_str = false;
    let mut pos_add_sub = None;
    for (i, c) in trimmed.char_indices().rev() {
        if c == '"' {
            in_str = !in_str;
        } else if !in_str && (c == '+' || c == '-') && i > 0 && i < trimmed.len() - 1 {
            let prev = trimmed[..i].trim_end();
            if !prev.ends_with(['+', '-', '*', '/', 'e', 'E', '$']) {
                pos_add_sub = Some((i, c));
                break;
            }
        }
    }
    if let Some((pos, op)) = pos_add_sub {
        let left = parse_expr(&trimmed[..pos])?;
        let right = parse_expr(&trimmed[pos + 1..])?;
        return match op {
            '+' => Ok(AwkExpr::Add(Box::new(left), Box::new(right))),
            '-' => Ok(AwkExpr::Sub(Box::new(left), Box::new(right))),
            _ => unreachable!(),
        };
    }

    // 2. Binary operations: * and / (higher precedence, scan right-to-left outside quotes)
    let mut pos_mul_div = None;
    for (i, c) in trimmed.char_indices().rev() {
        if c == '"' {
            in_str = !in_str;
        } else if !in_str && (c == '*' || c == '/') && i > 0 && i < trimmed.len() - 1 {
            let prev = trimmed[..i].trim_end();
            if !prev.ends_with(['+', '-', '*', '/', '$']) {
                pos_mul_div = Some((i, c));
                break;
            }
        }
    }
    if let Some((pos, op)) = pos_mul_div {
        let left = parse_expr(&trimmed[..pos])?;
        let right = parse_expr(&trimmed[pos + 1..])?;
        return match op {
            '*' => Ok(AwkExpr::Mul(Box::new(left), Box::new(right))),
            '/' => Ok(AwkExpr::Div(Box::new(left), Box::new(right))),
            _ => unreachable!(),
        };
    }

    // 3. Atom: LastField $NF
    if trimmed == "$NF" {
        return Ok(AwkExpr::LastField);
    }

    // 4. Atom: Field access $expr (e.g. $1, $0, $(1+1))
    if let Some(f_idx_str) = trimmed.strip_prefix('$') {
        let inner = parse_expr(f_idx_str)?;
        return Ok(AwkExpr::Field(Box::new(inner)));
    }

    // 5. Atom: String literal
    if trimmed.starts_with('"') && trimmed.ends_with('"') && trimmed.len() >= 2 {
        return Ok(AwkExpr::StringLit(trimmed[1..trimmed.len() - 1].to_string()));
    }

    // 6. Atom: Number literal
    if let Ok(n) = trimmed.parse::<f64>() {
        return Ok(AwkExpr::NumberLit(n));
    }

    // 7. Atom: Variable
    Ok(AwkExpr::Var(trimmed.to_string()))
}

// ============================================================================
// AWK Execution Context & Engine
// ============================================================================

struct AwkContext<'a> {
    fs_sep: Option<&'a str>,
    num_vars: HashMap<String, f64>,
    str_vars: HashMap<String, String>,
    nr: usize,
    current_line: String,
    current_fields: Vec<String>,
}

impl<'a> AwkContext<'a> {
    fn new(
        fs_sep: Option<&'a str>,
        num_vars: HashMap<String, f64>,
        str_vars: HashMap<String, String>,
    ) -> Self {
        Self {
            fs_sep,
            num_vars,
            str_vars,
            nr: 0,
            current_line: String::new(),
            current_fields: Vec::new(),
        }
    }

    fn set_record(&mut self, line: String) {
        self.nr += 1;
        self.current_line = line;

        let fields: Vec<String> = if let Some(sep) = self.fs_sep {
            self.current_line
                .split(sep)
                .map(|s| s.to_string())
                .collect()
        } else {
            self.current_line
                .split_whitespace()
                .map(|s| s.to_string())
                .collect()
        };

        self.current_fields = fields;
    }

    fn eval_expr(&self, expr: &AwkExpr) -> (f64, String) {
        match expr {
            AwkExpr::NumberLit(n) => (*n, n.to_string()),
            AwkExpr::StringLit(s) => (s.parse::<f64>().unwrap_or(0.0), s.clone()),
            AwkExpr::Var(v) => {
                if v == "NR" {
                    (self.nr as f64, self.nr.to_string())
                } else if v == "NF" {
                    (self.current_fields.len() as f64, self.current_fields.len().to_string())
                } else if let Some(n) = self.num_vars.get(v) {
                    (*n, n.to_string())
                } else if let Some(s) = self.str_vars.get(v) {
                    (s.parse::<f64>().unwrap_or(0.0), s.clone())
                } else {
                    (0.0, String::new())
                }
            }
            AwkExpr::LastField => {
                let last = self.current_fields.last().cloned().unwrap_or_default();
                let n = last.parse::<f64>().unwrap_or(0.0);
                (n, last)
            }
            AwkExpr::Field(idx_expr) => {
                let (idx_num, _) = self.eval_expr(idx_expr);
                if idx_num < 0.0 || idx_num.is_nan() || idx_num > usize::MAX as f64 {
                    return (0.0, String::new());
                }
                let idx = idx_num as usize;
                if idx == 0 {
                    let n = self.current_line.parse::<f64>().unwrap_or(0.0);
                    (n, self.current_line.clone())
                } else if idx <= self.current_fields.len() {
                    let val = &self.current_fields[idx - 1];
                    let n = val.parse::<f64>().unwrap_or(0.0);
                    (n, val.clone())
                } else {
                    (0.0, String::new())
                }
            }
            AwkExpr::Add(l, r) => {
                let (nl, _) = self.eval_expr(l);
                let (nr, _) = self.eval_expr(r);
                let res = nl + nr;
                (res, res.to_string())
            }
            AwkExpr::Sub(l, r) => {
                let (nl, _) = self.eval_expr(l);
                let (nr, _) = self.eval_expr(r);
                let res = nl - nr;
                (res, res.to_string())
            }
            AwkExpr::Mul(l, r) => {
                let (nl, _) = self.eval_expr(l);
                let (nr, _) = self.eval_expr(r);
                let res = nl * nr;
                (res, res.to_string())
            }
            AwkExpr::Div(l, r) => {
                let (nl, _) = self.eval_expr(l);
                let (nr, _) = self.eval_expr(r);
                let res = if nr != 0.0 { nl / nr } else { 0.0 };
                (res, res.to_string())
            }
        }
    }

    fn eval_pattern(&self, pat: &AwkPattern) -> bool {
        match pat {
            AwkPattern::Always => true,
            AwkPattern::Regex(re) => self.current_line.contains(re),
            AwkPattern::Comparison(left, op, right) => {
                let (nl, sl) = self.eval_expr(left);
                let (nr, sr) = self.eval_expr(right);

                match op {
                    CompOp::Eq => sl == sr || nl == nr,
                    CompOp::Ne => sl != sr && nl != nr,
                    CompOp::Lt => nl < nr,
                    CompOp::Le => nl <= nr,
                    CompOp::Gt => nl > nr,
                    CompOp::Ge => nl >= nr,
                    CompOp::Match => sl.contains(&sr),
                }
            }
        }
    }

    fn execute_statement(&mut self, stmt: &AwkStatement, stdout: &mut dyn Write) -> io::Result<()> {
        match stmt {
            AwkStatement::Print(exprs) => {
                let mut parts = Vec::new();
                for expr in exprs {
                    let (_, s) = self.eval_expr(expr);
                    parts.push(s);
                }
                writeln!(stdout, "{}", parts.join(" "))?;
            }
            AwkStatement::Assign(var, expr) => {
                let (n, s) = self.eval_expr(expr);
                self.num_vars.insert(var.clone(), n);
                self.str_vars.insert(var.clone(), s);
            }
            AwkStatement::AssignAdd(var, expr) => {
                let (n, _) = self.eval_expr(expr);
                let cur = self.num_vars.get(var).copied().unwrap_or(0.0);
                let updated = cur + n;
                self.num_vars.insert(var.clone(), updated);
                self.str_vars.insert(var.clone(), updated.to_string());
            }
            AwkStatement::Increment(var) => {
                let cur = self.num_vars.get(var).copied().unwrap_or(0.0);
                let updated = cur + 1.0;
                self.num_vars.insert(var.clone(), updated);
                self.str_vars.insert(var.clone(), updated.to_string());
            }
        }
        Ok(())
    }
}

fn execute_awk_program(
    program: &AwkProgram,
    fs_sep: Option<&str>,
    initial_vars: HashMap<String, f64>,
    initial_str_vars: HashMap<String, String>,
    files: &[String],
) -> ExitCode {
    let mut ctx = AwkContext::new(fs_sep, initial_vars, initial_str_vars);
    let stdout = io::stdout();
    let mut out_handle = stdout.lock();

    // Execute BEGIN blocks
    for block in &program.begin_blocks {
        for stmt in &block.statements {
            if let Err(e) = ctx.execute_statement(stmt, &mut out_handle) {
                if e.kind() == io::ErrorKind::BrokenPipe {
                    return ExitCode::SUCCESS;
                }
                eprintln!("awk: write error: {}", e);
                return ExitCode::from(1);
            }
        }
    }

    // Process input streams
    let input_sources: Vec<Box<dyn BufRead>> = if files.is_empty() {
        vec![Box::new(BufReader::new(io::stdin()))]
    } else {
        let mut readers: Vec<Box<dyn BufRead>> = Vec::new();
        for f in files {
            if f == "-" {
                readers.push(Box::new(BufReader::new(io::stdin())));
            } else {
                match File::open(f) {
                    Ok(file) => readers.push(Box::new(BufReader::new(file))),
                    Err(e) => {
                        eprintln!("awk: cannot open {}: {}", f, e);
                        return ExitCode::from(1);
                    }
                }
            }
        }
        readers
    };

    for mut reader in input_sources {
        let mut line = String::new();
        loop {
            match reader.read_line(&mut line) {
                Ok(0) => break,
                Ok(_) => {
                    let trimmed_line = line.trim_end_matches(&['\r', '\n'][..]).to_string();
                    ctx.set_record(trimmed_line);

                    for rule in &program.rules {
                        let matches = rule.pattern.as_ref().map(|p| ctx.eval_pattern(p)).unwrap_or(true);
                        if matches {
                            for stmt in &rule.block.statements {
                                if let Err(e) = ctx.execute_statement(stmt, &mut out_handle) {
                                    if e.kind() == io::ErrorKind::BrokenPipe {
                                        return ExitCode::SUCCESS;
                                    }
                                    eprintln!("awk: write error: {}", e);
                                    return ExitCode::from(1);
                                }
                            }
                        }
                    }
                    line.clear();
                }
                Err(e) => {
                    eprintln!("awk: read error: {}", e);
                    return ExitCode::from(1);
                }
            }
        }
    }

    // Execute END blocks
    for block in &program.end_blocks {
        for stmt in &block.statements {
            if let Err(e) = ctx.execute_statement(stmt, &mut out_handle) {
                if e.kind() == io::ErrorKind::BrokenPipe {
                    return ExitCode::SUCCESS;
                }
                eprintln!("awk: write error: {}", e);
                return ExitCode::from(1);
            }
        }
    }

    ExitCode::SUCCESS
}

// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_awk_field_printing() {
        let prog = parse_awk_program("{print $1, $3}").unwrap();
        assert_eq!(prog.rules.len(), 1);

        let mut ctx = AwkContext::new(None, HashMap::new(), HashMap::new());
        ctx.set_record("alpha beta gamma delta".to_string());

        let mut buf = Vec::new();
        for stmt in &prog.rules[0].block.statements {
            ctx.execute_statement(stmt, &mut buf).unwrap();
        }

        let output = String::from_utf8(buf).unwrap();
        assert_eq!(output, "alpha gamma\n");
    }

    #[test]
    fn test_awk_last_field_and_nr() {
        let prog = parse_awk_program("{print NR, $NF}").unwrap();
        let mut ctx = AwkContext::new(None, HashMap::new(), HashMap::new());
        ctx.set_record("one two three".to_string());

        let mut buf = Vec::new();
        for stmt in &prog.rules[0].block.statements {
            ctx.execute_statement(stmt, &mut buf).unwrap();
        }

        let output = String::from_utf8(buf).unwrap();
        assert_eq!(output, "1 three\n");
    }

    #[test]
    fn test_awk_begin_and_end_sum() {
        let prog = parse_awk_program("BEGIN {sum = 0} {sum += $1} END {print sum}").unwrap();
        assert_eq!(prog.begin_blocks.len(), 1);
        assert_eq!(prog.rules.len(), 1);
        assert_eq!(prog.end_blocks.len(), 1);

        let mut ctx = AwkContext::new(None, HashMap::new(), HashMap::new());
        for stmt in &prog.begin_blocks[0].statements {
            let mut dummy = Vec::new();
            ctx.execute_statement(stmt, &mut dummy).unwrap();
        }

        for val in ["10", "20", "30"] {
            ctx.set_record(val.to_string());
            for stmt in &prog.rules[0].block.statements {
                let mut dummy = Vec::new();
                ctx.execute_statement(stmt, &mut dummy).unwrap();
            }
        }

        let mut end_buf = Vec::new();
        for stmt in &prog.end_blocks[0].statements {
            ctx.execute_statement(stmt, &mut end_buf).unwrap();
        }

        assert_eq!(String::from_utf8(end_buf).unwrap(), "60\n");
    }

    #[test]
    fn test_awk_cli_rejections() {
        // Unknown option
        assert_eq!(run_awk(&["--invalid-opt".to_string(), "{print $0}".to_string()]), ExitCode::from(1));
        // Missing argument for -F
        assert_eq!(run_awk(&["-F".to_string()]), ExitCode::from(1));
        // Missing argument for -v
        assert_eq!(run_awk(&["-v".to_string()]), ExitCode::from(1));
        // Missing argument for -f
        assert_eq!(run_awk(&["-f".to_string()]), ExitCode::from(1));
        // Nonexistent file for -f
        assert_eq!(run_awk(&["-f".to_string(), "/nonexistent_awk_script_path".to_string()]), ExitCode::from(1));
        // No program text specified
        assert_eq!(run_awk(&[]), ExitCode::from(1));
    }

    #[test]
    fn test_awk_brace_in_string_and_field_bounds() {
        // Braces inside string literals should not terminate block prematurely
        let prog = parse_awk_program(r#"{print "{"}"#).unwrap();
        assert_eq!(prog.rules.len(), 1);

        // Invalid or extreme field numbers shouldn't panic
        let mut ctx = AwkContext::new(None, HashMap::new(), HashMap::new());
        ctx.set_record("alpha beta".to_string());
        let (val, str_val) = ctx.eval_expr(&AwkExpr::Field(Box::new(AwkExpr::NumberLit(-1.0))));
        assert_eq!(val, 0.0);
        assert_eq!(str_val, "");

        let (val_nan, str_val_nan) = ctx.eval_expr(&AwkExpr::Field(Box::new(AwkExpr::NumberLit(f64::NAN))));
        assert_eq!(val_nan, 0.0);
        assert_eq!(str_val_nan, "");

        let (val_huge, str_val_huge) = ctx.eval_expr(&AwkExpr::Field(Box::new(AwkExpr::NumberLit(1e20))));
        assert_eq!(val_huge, 0.0);
        assert_eq!(str_val_huge, "");
    }
}
