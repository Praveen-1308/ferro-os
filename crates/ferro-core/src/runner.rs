//! ferro-core runner: Pure-Rust Multi-Language Code Runner, Micro-Compiler & Modern REPL.
//!
//! Provides zero-dependency, self-contained developer ergonomics for FerroOS:
//! - `eval "<expr>"`: Instant mathematical, bitwise, and logic expression evaluator.
//! - `run <file.ext>`: Universal code runner supporting `.sh`, `.py`, `.c`, `.rs`, and `.ferro`.
//! - Pure-Rust Micro-Script Engine: AST-based lightweight interpreter with variables, control flow, file I/O, and sys calls.
//! - Modern Interactive REPL (`ferro-core run --repl`): Live interactive scratchpad and calculator.

#![allow(clippy::all)]

use std::collections::HashMap;
use std::fs;
use std::io::{self, BufRead, Read, Write};
use std::net::TcpStream;
use std::path::Path;
use std::process::{Command, ExitCode};

// ==============================================================================
// 1. Expression Evaluator (`eval` / calculator)
// ==============================================================================

#[derive(Debug, Clone, PartialEq)]
pub enum Token {
    Number(i64),
    Plus,
    Minus,
    Star,
    Slash,
    Percent,
    Ampersand,
    Pipe,
    Caret,
    Shl,
    Shr,
    LParen,
    RParen,
    EqEq,
    NotEq,
    Lt,
    Gt,
    Le,
    Ge,
    Ident(String),
}

pub fn tokenize_expr(input: &str) -> Result<Vec<Token>, String> {
    let mut tokens = Vec::new();
    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;

    while i < chars.len() {
        let c = chars[i];
        if c.is_whitespace() {
            i += 1;
            continue;
        }

        if c.is_ascii_digit() || (c == '0' && i + 1 < chars.len() && (chars[i + 1] == 'x' || chars[i + 1] == 'b')) {
            let start = i;
            let is_hex = c == '0' && i + 1 < chars.len() && chars[i + 1] == 'x';
            let is_bin = c == '0' && i + 1 < chars.len() && chars[i + 1] == 'b';

            if is_hex || is_bin {
                i += 2;
                while i < chars.len() && (chars[i].is_ascii_hexdigit() || chars[i] == '_') {
                    i += 1;
                }
            } else {
                while i < chars.len() && (chars[i].is_ascii_digit() || chars[i] == '_') {
                    i += 1;
                }
            }

            let num_str: String = chars[start..i].iter().filter(|&&ch| ch != '_').collect();
            let val = if is_hex {
                i64::from_str_radix(num_str.trim_start_matches("0x"), 16)
                    .map_err(|e| format!("Invalid hex constant '{}': {}", num_str, e))?
            } else if is_bin {
                i64::from_str_radix(num_str.trim_start_matches("0b"), 2)
                    .map_err(|e| format!("Invalid binary constant '{}': {}", num_str, e))?
            } else {
                num_str.parse::<i64>().map_err(|e| format!("Invalid integer '{}': {}", num_str, e))?
            };

            tokens.push(Token::Number(val));
            continue;
        }

        if c.is_ascii_alphabetic() || c == '_' {
            let start = i;
            while i < chars.len() && (chars[i].is_ascii_alphanumeric() || chars[i] == '_') {
                i += 1;
            }
            let ident: String = chars[start..i].iter().collect();
            tokens.push(Token::Ident(ident));
            continue;
        }

        match c {
            '+' => tokens.push(Token::Plus),
            '-' => tokens.push(Token::Minus),
            '*' => tokens.push(Token::Star),
            '/' => tokens.push(Token::Slash),
            '%' => tokens.push(Token::Percent),
            '&' => tokens.push(Token::Ampersand),
            '|' => tokens.push(Token::Pipe),
            '^' => tokens.push(Token::Caret),
            '(' => tokens.push(Token::LParen),
            ')' => tokens.push(Token::RParen),
            '<' => {
                if i + 1 < chars.len() && chars[i + 1] == '<' {
                    tokens.push(Token::Shl);
                    i += 1;
                } else if i + 1 < chars.len() && chars[i + 1] == '=' {
                    tokens.push(Token::Le);
                    i += 1;
                } else {
                    tokens.push(Token::Lt);
                }
            }
            '>' => {
                if i + 1 < chars.len() && chars[i + 1] == '>' {
                    tokens.push(Token::Shr);
                    i += 1;
                } else if i + 1 < chars.len() && chars[i + 1] == '=' {
                    tokens.push(Token::Ge);
                    i += 1;
                } else {
                    tokens.push(Token::Gt);
                }
            }
            '=' => {
                if i + 1 < chars.len() && chars[i + 1] == '=' {
                    tokens.push(Token::EqEq);
                    i += 1;
                }
            }
            '!' => {
                if i + 1 < chars.len() && chars[i + 1] == '=' {
                    tokens.push(Token::NotEq);
                    i += 1;
                }
            }
            _ => return Err(format!("Unexpected character '{}' in expression", c)),
        }
        i += 1;
    }

    Ok(tokens)
}

pub fn evaluate_expression(input: &str, vars: &HashMap<String, i64>) -> Result<i64, String> {
    let tokens = tokenize_expr(input)?;
    if tokens.is_empty() {
        return Ok(0);
    }
    let mut parser = ExprParser { tokens, pos: 0, vars };
    parser.parse_or()
}

struct ExprParser<'a> {
    tokens: Vec<Token>,
    pos: usize,
    vars: &'a HashMap<String, i64>,
}

impl<'a> ExprParser<'a> {
    fn peek(&self) -> Option<&Token> {
        self.tokens.get(self.pos)
    }

    fn next(&mut self) -> Option<Token> {
        if self.pos < self.tokens.len() {
            let tok = self.tokens[self.pos].clone();
            self.pos += 1;
            Some(tok)
        } else {
            None
        }
    }

    fn parse_or(&mut self) -> Result<i64, String> {
        let mut left = self.parse_xor()?;
        while let Some(Token::Pipe) = self.peek() {
            self.next();
            let right = self.parse_xor()?;
            left |= right;
        }
        Ok(left)
    }

    fn parse_xor(&mut self) -> Result<i64, String> {
        let mut left = self.parse_and()?;
        while let Some(Token::Caret) = self.peek() {
            self.next();
            let right = self.parse_and()?;
            left ^= right;
        }
        Ok(left)
    }

    fn parse_and(&mut self) -> Result<i64, String> {
        let mut left = self.parse_equality()?;
        while let Some(Token::Ampersand) = self.peek() {
            self.next();
            let right = self.parse_equality()?;
            left &= right;
        }
        Ok(left)
    }

    fn parse_equality(&mut self) -> Result<i64, String> {
        let mut left = self.parse_relational()?;
        while let Some(tok) = self.peek() {
            match tok {
                Token::EqEq => {
                    self.next();
                    let right = self.parse_relational()?;
                    left = if left == right { 1 } else { 0 };
                }
                Token::NotEq => {
                    self.next();
                    let right = self.parse_relational()?;
                    left = if left != right { 1 } else { 0 };
                }
                _ => break,
            }
        }
        Ok(left)
    }

    fn parse_relational(&mut self) -> Result<i64, String> {
        let mut left = self.parse_shift()?;
        while let Some(tok) = self.peek() {
            match tok {
                Token::Lt => {
                    self.next();
                    let right = self.parse_shift()?;
                    left = if left < right { 1 } else { 0 };
                }
                Token::Gt => {
                    self.next();
                    let right = self.parse_shift()?;
                    left = if left > right { 1 } else { 0 };
                }
                Token::Le => {
                    self.next();
                    let right = self.parse_shift()?;
                    left = if left <= right { 1 } else { 0 };
                }
                Token::Ge => {
                    self.next();
                    let right = self.parse_shift()?;
                    left = if left >= right { 1 } else { 0 };
                }
                _ => break,
            }
        }
        Ok(left)
    }

    fn parse_shift(&mut self) -> Result<i64, String> {
        let mut left = self.parse_term()?;
        while let Some(tok) = self.peek() {
            match tok {
                Token::Shl => {
                    self.next();
                    let right = self.parse_term()?;
                    left = left.wrapping_shl(right as u32);
                }
                Token::Shr => {
                    self.next();
                    let right = self.parse_term()?;
                    left = left.wrapping_shr(right as u32);
                }
                _ => break,
            }
        }
        Ok(left)
    }

    fn parse_term(&mut self) -> Result<i64, String> {
        let mut left = self.parse_factor()?;
        while let Some(tok) = self.peek() {
            match tok {
                Token::Plus => {
                    self.next();
                    let right = self.parse_factor()?;
                    left = left.wrapping_add(right);
                }
                Token::Minus => {
                    self.next();
                    let right = self.parse_factor()?;
                    left = left.wrapping_sub(right);
                }
                _ => break,
            }
        }
        Ok(left)
    }

    fn parse_factor(&mut self) -> Result<i64, String> {
        let mut left = self.parse_primary()?;
        while let Some(tok) = self.peek() {
            match tok {
                Token::Star => {
                    self.next();
                    let right = self.parse_primary()?;
                    left = left.wrapping_mul(right);
                }
                Token::Slash => {
                    self.next();
                    let right = self.parse_primary()?;
                    if right == 0 {
                        return Err("Division by zero error".to_string());
                    }
                    left /= right;
                }
                Token::Percent => {
                    self.next();
                    let right = self.parse_primary()?;
                    if right == 0 {
                        return Err("Modulo by zero error".to_string());
                    }
                    left %= right;
                }
                _ => break,
            }
        }
        Ok(left)
    }

    fn parse_primary(&mut self) -> Result<i64, String> {
        match self.next() {
            Some(Token::Number(n)) => Ok(n),
            Some(Token::Ident(name)) => {
                if let Some(&val) = self.vars.get(&name) {
                    Ok(val)
                } else if name == "true" {
                    Ok(1)
                } else if name == "false" {
                    Ok(0)
                } else {
                    Err(format!("Undefined variable '{}'", name))
                }
            }
            Some(Token::Minus) => {
                let val = self.parse_primary()?;
                Ok(-val)
            }
            Some(Token::LParen) => {
                let inner = self.parse_or()?;
                if let Some(Token::RParen) = self.next() {
                    Ok(inner)
                } else {
                    Err("Missing closing parenthesis ')'".to_string())
                }
            }
            other => Err(format!("Unexpected token in expression: {:?}", other)),
        }
    }
}

// ==============================================================================
// 2. Pure-Rust Micro-Script Engine & Universal Runner
// ==============================================================================

pub fn http_get_sync(url: &str) -> Result<String, String> {
    if url.starts_with("http://") {
        let without_proto = &url[7..];
        let (host, path) = match without_proto.find('/') {
            Some(pos) => (&without_proto[..pos], &without_proto[pos..]),
            None => (without_proto, "/"),
        };
        let (host_name, port) = match host.find(':') {
            Some(pos) => (&host[..pos], host[pos + 1..].parse::<u16>().unwrap_or(80)),
            None => (host, 80),
        };
        let mut stream = TcpStream::connect((host_name, port))
            .map_err(|e| format!("Connect failed to {}:{}: {}", host_name, port, e))?;
        let request = format!(
            "GET {} HTTP/1.1\r\nHost: {}\r\nUser-Agent: FerroOS-PureRust/2.3\r\nConnection: close\r\n\r\n",
            path, host_name
        );
        stream.write_all(request.as_bytes()).map_err(|e| e.to_string())?;
        let mut response = Vec::new();
        stream.read_to_end(&mut response).map_err(|e| e.to_string())?;
        let header_sep = b"\r\n\r\n";
        let body_start = response
            .windows(4)
            .position(|w| w == header_sep)
            .map(|p| p + 4)
            .unwrap_or(0);
        return String::from_utf8(response[body_start..].to_vec()).map_err(|e| e.to_string());
    }

    if url.starts_with("https://") {
        let output = Command::new("curl")
            .args(["-s", "-L", url])
            .output();
        if let Ok(out) = output {
            if out.status.success() {
                return String::from_utf8(out.stdout).map_err(|e| e.to_string());
            }
        }
        return Err(format!("https request failed: TLS requires curl on host: {}", url));
    }

    Err(format!("Unsupported protocol for URL: {}", url))
}

pub fn json_get(raw_json: &str, key: &str) -> Option<String> {
    let clean = raw_json.replace("\\\"", "\"");
    let needle1 = format!("\"{}\":", key);
    let needle2 = format!("\"{}\" :", key);
    let pos = clean.find(&needle1).map(|p| p + needle1.len())
        .or_else(|| clean.find(&needle2).map(|p| p + needle2.len()))?;
    let rest = clean[pos..].trim_start();
    if rest.starts_with('"') {
        let after_quote = &rest[1..];
        let end_quote = after_quote.find('"')?;
        Some(after_quote[..end_quote].to_string())
    } else {
        let end = rest.find(|c: char| c == ',' || c == '}' || c == ']' || c == '\n' || c == '\r')
            .unwrap_or(rest.len());
        Some(rest[..end].trim().to_string())
    }
}

pub struct MicroScriptEngine {
    pub vars: HashMap<String, i64>,
    pub string_vars: HashMap<String, String>,
}

impl MicroScriptEngine {
    pub fn new() -> Self {
        Self {
            vars: HashMap::new(),
            string_vars: HashMap::new(),
        }
    }

    pub fn eval_string_expr(&self, raw: &str) -> Option<String> {
        let trimmed = raw.trim();

        // Check for concatenation (+) if not inside a single quote
        if trimmed.contains('+') && !trimmed.starts_with("http://") && !trimmed.starts_with("https://") {
            let mut parts = Vec::new();
            let mut current = String::new();
            let mut in_quote = false;
            let mut in_paren: usize = 0;
            for c in trimmed.chars() {
                if c == '"' {
                    in_quote = !in_quote;
                    current.push(c);
                } else if c == '(' && !in_quote {
                    in_paren += 1;
                    current.push(c);
                } else if c == ')' && !in_quote {
                    in_paren = in_paren.saturating_sub(1);
                    current.push(c);
                } else if c == '+' && !in_quote && in_paren == 0 {
                    parts.push(current.trim().to_string());
                    current.clear();
                } else {
                    current.push(c);
                }
            }
            if !current.trim().is_empty() {
                parts.push(current.trim().to_string());
            }

            if parts.len() > 1 {
                // Must contain at least one string atom to be a string concatenation expression
                let has_string_atom = parts.iter().any(|p| self.eval_string_atom(p).is_some());
                if !has_string_atom {
                    return None;
                }

                let mut combined = String::new();
                for p in parts {
                    if let Some(s) = self.eval_string_atom(&p) {
                        combined.push_str(&s);
                    } else if let Ok(val) = evaluate_expression(&p, &self.vars) {
                        combined.push_str(&val.to_string());
                    } else if let Some(&val) = self.vars.get(&p) {
                        combined.push_str(&val.to_string());
                    } else {
                        combined.push_str(&p);
                    }
                }
                return Some(combined);
            }
        }

        self.eval_string_atom(trimmed)
    }

    fn eval_string_atom(&self, raw: &str) -> Option<String> {
        let trimmed = raw.trim();

        // 1. Literal quoted string: "..."
        if trimmed.starts_with('"') && trimmed.ends_with('"') && trimmed.len() >= 2 {
            let inner = &trimmed[1..trimmed.len() - 1];
            let unescaped = inner.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", "\"");
            return Some(unescaped);
        }

        // 2. http_get(...)
        if trimmed.starts_with("http_get(") && trimmed.ends_with(')') {
            let inner = trimmed.trim_start_matches("http_get(").trim_end_matches(')').trim();
            let url = self.eval_string_expr(inner).unwrap_or_else(|| inner.trim_matches('"').to_string());
            return http_get_sync(&url).ok();
        }

        // 3. json_get(json_source, "key")
        if trimmed.starts_with("json_get(") && trimmed.ends_with(')') {
            let inner = trimmed.trim_start_matches("json_get(").trim_end_matches(')').trim();
            // Split by comma outside quotes
            let mut split_pos = None;
            let mut in_quote = false;
            for (idx, c) in inner.char_indices() {
                if c == '"' { in_quote = !in_quote; }
                else if c == ',' && !in_quote { split_pos = Some(idx); }
            }
            if let Some(pos) = split_pos {
                let json_src_raw = &inner[..pos];
                let key_raw = &inner[pos + 1..];
                let json_src = self.eval_string_expr(json_src_raw.trim()).unwrap_or_else(|| json_src_raw.trim().to_string());
                let key = self.eval_string_expr(key_raw.trim()).unwrap_or_else(|| key_raw.trim().trim_matches('"').to_string());
                return json_get(&json_src, &key);
            }
        }

        // 4. read_file(path)
        if trimmed.starts_with("read_file(") && trimmed.ends_with(')') {
            let inner = trimmed.trim_start_matches("read_file(").trim_end_matches(')').trim();
            let path = self.eval_string_expr(inner).unwrap_or_else(|| inner.trim_matches('"').to_string());
            return fs::read_to_string(&path).ok();
        }

        // 5. sys_env("KEY")
        if trimmed.starts_with("sys_env(") && trimmed.ends_with(')') {
            let inner = trimmed.trim_start_matches("sys_env(").trim_end_matches(')').trim();
            let key = self.eval_string_expr(inner).unwrap_or_else(|| inner.trim_matches('"').to_string());
            return std::env::var(&key).ok();
        }

        // 6. Variable lookup
        if let Some(s) = self.string_vars.get(trimmed) {
            return Some(s.clone());
        }

        None
    }

    pub fn execute(&mut self, source: &str) -> Result<(), String> {
        let lines: Vec<&str> = source.lines().collect();
        let mut i = 0;

        while i < lines.len() {
            let line = lines[i].trim();
            if line.is_empty() || line.starts_with("//") || line.starts_with('#') {
                i += 1;
                continue;
            }

            // Control flow: if <condition> { ... }
            if line.starts_with("if ") {
                let cond_str = line.trim_start_matches("if ").trim_end_matches('{').trim();
                let cond_val = evaluate_expression(cond_str, &self.vars).unwrap_or(0);
                let mut brace_depth = 1;
                let start_idx = i + 1;
                let mut end_idx = start_idx;
                while end_idx < lines.len() && brace_depth > 0 {
                    if lines[end_idx].contains('{') { brace_depth += 1; }
                    if lines[end_idx].contains('}') { brace_depth -= 1; }
                    if brace_depth == 0 { break; }
                    end_idx += 1;
                }
                if cond_val != 0 {
                    let block = lines[start_idx..end_idx].join("\n");
                    self.execute(&block)?;
                }
                i = end_idx + 1;
                continue;
            }

            // Control flow: while <condition> { ... }
            if line.starts_with("while ") {
                let cond_str = line.trim_start_matches("while ").trim_end_matches('{').trim().to_string();
                let mut brace_depth = 1;
                let start_idx = i + 1;
                let mut end_idx = start_idx;
                while end_idx < lines.len() && brace_depth > 0 {
                    if lines[end_idx].contains('{') { brace_depth += 1; }
                    if lines[end_idx].contains('}') { brace_depth -= 1; }
                    if brace_depth == 0 { break; }
                    end_idx += 1;
                }
                let block = lines[start_idx..end_idx].join("\n");
                let mut iterations = 0;
                while evaluate_expression(&cond_str, &self.vars).unwrap_or(0) != 0 {
                    self.execute(&block)?;
                    iterations += 1;
                    if iterations > 100_000 {
                        return Err("Infinite loop detected in while block".to_string());
                    }
                }
                i = end_idx + 1;
                continue;
            }

            // Built-in: write_file("path", content)
            if line.starts_with("write_file(") {
                let args_str = line.trim_start_matches("write_file(").trim_end_matches(';').trim_end_matches(')');
                if let Some((p_raw, c_raw)) = args_str.split_once(',') {
                    let path = self.eval_string_expr(p_raw.trim()).unwrap_or_else(|| p_raw.trim().trim_matches('"').to_string());
                    let content = self.eval_string_expr(c_raw.trim()).unwrap_or_else(|| c_raw.trim().to_string());
                    let _ = fs::write(&path, content);
                }
                i += 1;
                continue;
            }

            // Built-in: append_file("path", content)
            if line.starts_with("append_file(") {
                let args_str = line.trim_start_matches("append_file(").trim_end_matches(';').trim_end_matches(')');
                if let Some((p_raw, c_raw)) = args_str.split_once(',') {
                    let path = self.eval_string_expr(p_raw.trim()).unwrap_or_else(|| p_raw.trim().trim_matches('"').to_string());
                    let content = self.eval_string_expr(c_raw.trim()).unwrap_or_else(|| c_raw.trim().to_string());
                    use std::fs::OpenOptions;
                    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(&path) {
                        let _ = f.write_all(content.as_bytes());
                    }
                }
                i += 1;
                continue;
            }

            // Built-in: sys("command") or sys command
            if line.starts_with("sys(") || line.starts_with("sys ") {
                let cmd_arg = if line.starts_with("sys(") {
                    line.trim_start_matches("sys(").trim_end_matches(';').trim_end_matches(')').trim().trim_matches('"')
                } else {
                    line["sys".len()..].trim().trim_end_matches(';').trim_matches('"')
                };
                let _ = Command::new("/bin/sh").arg("-c").arg(cmd_arg).status();
                i += 1;
                continue;
            }

            // Variable assignment: `let x = <expr>;` or `x = <expr>;`
            if line.starts_with("let ") || (line.contains('=') && !line.contains("==")) {
                let clean = line.trim_start_matches("let ").trim_end_matches(';');
                if let Some((lhs, rhs)) = clean.split_once('=') {
                    let var_name = lhs.trim().to_string();
                    let raw_rhs = rhs.trim();

                    if raw_rhs.starts_with("len(") && raw_rhs.ends_with(')') {
                        let inner = raw_rhs.trim_start_matches("len(").trim_end_matches(')').trim();
                        let l = self.string_vars.get(inner).map(|s| s.len() as i64).unwrap_or(0);
                        self.vars.insert(var_name, l);
                    } else if let Some(str_val) = self.eval_string_expr(raw_rhs) {
                        self.string_vars.insert(var_name, str_val);
                    } else {
                        let evaluated = evaluate_expression(raw_rhs, &self.vars)?;
                        self.vars.insert(var_name, evaluated);
                    }
                }
                i += 1;
                continue;
            }

            // Built-in: print(...) / println(...) or print ... / println ...
            if line.starts_with("println") || line.starts_with("print") {
                let is_nl = line.starts_with("println");
                let rest = if is_nl {
                    &line["println".len()..]
                } else {
                    &line["print".len()..]
                };
                let rest_trimmed = rest.trim();
                let inner = if rest_trimmed.starts_with('(') && rest_trimmed.ends_with(')') {
                    &rest_trimmed[1..rest_trimmed.len() - 1]
                } else {
                    rest_trimmed
                }.trim_end_matches(';').trim();

                if let Some(text) = self.eval_string_expr(inner) {
                    if is_nl {
                        println!("{}", text);
                    } else {
                        print!("{}", text);
                        let _ = io::stdout().flush();
                    }
                } else if let Ok(val) = evaluate_expression(inner, &self.vars) {
                    if is_nl {
                        println!("{}", val);
                    } else {
                        print!("{}", val);
                        let _ = io::stdout().flush();
                    }
                } else {
                    if is_nl {
                        println!("{}", inner);
                    } else {
                        print!("{}", inner);
                        let _ = io::stdout().flush();
                    }
                }
                i += 1;
                continue;
            }

            // Default: attempt expression evaluation
            let _ = evaluate_expression(line.trim_end_matches(';'), &self.vars);
            i += 1;
        }

        Ok(())
    }
}

// ==============================================================================
// 3. Interactive Code REPL & Applet Dispatch
// ==============================================================================

pub fn run_repl() -> ExitCode {
    println!("================================================================================");
    println!("        FERRO-OS MODERN INTERACTIVE CODE REPL & CALCULATOR (Rust)               ");
    println!("================================================================================");
    println!("• Evaluate arithmetic/bitwise expressions: '1024 * 64', '0xDEAD ^ 0xBEEF'");
    println!("• Assign variables: 'let x = 42', 'let y = x * 2'");
    println!("• Run system commands: ':sh <cmd>' or 'sys(\"ls -l\")'");
    println!("• Type ':help' for manual, or ':exit' / 'quit' to return.");
    println!("--------------------------------------------------------------------------------");

    let mut engine = MicroScriptEngine::new();
    let stdin = io::stdin();

    loop {
        print!("\x1b[1;36mferro-code>\x1b[0m ");
        let _ = io::stdout().flush();

        let mut line = String::new();
        if stdin.lock().read_line(&mut line).is_err() || line.is_empty() {
            break;
        }

        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        if trimmed == ":exit" || trimmed == ":quit" || trimmed == "quit" || trimmed == "exit" {
            break;
        }

        if trimmed == ":help" {
            println!("REPL Commands:");
            println!("  :vars              List active variables");
            println!("  :sh <command>      Run shell command");
            println!("  :clear             Clear screen");
            println!("  :exit              Exit REPL");
            continue;
        }

        if trimmed == ":vars" {
            println!("--- Integer Variables ---");
            for (k, v) in &engine.vars {
                println!("  {} = {} (0x{:X})", k, v, v);
            }
            println!("--- String Variables ---");
            for (k, v) in &engine.string_vars {
                println!("  {} = \"{}\"", k, v);
            }
            continue;
        }

        if trimmed == ":clear" {
            print!("\x1b[2J\x1b[H");
            let _ = io::stdout().flush();
            continue;
        }

        if let Some(cmd_str) = trimmed.strip_prefix(":sh ") {
            let _ = Command::new("/bin/sh").arg("-c").arg(cmd_str).status();
            continue;
        }

        // Try single-expression evaluation first
        match evaluate_expression(trimmed, &engine.vars) {
            Ok(result) => {
                println!("\x1b[1;32m=> {} (0x{:X}, 0b{:b})\x1b[0m", result, result, result);
            }
            Err(_) => {
                if let Some(s) = engine.eval_string_expr(trimmed) {
                    println!("\x1b[1;32m=> \"{}\"\x1b[0m", s);
                } else if let Err(e) = engine.execute(trimmed) {
                    println!("\x1b[1;31mError: {}\x1b[0m", e);
                }
            }
        }
    }

    println!("[ferro-code] Exited REPL.");
    ExitCode::SUCCESS
}

pub fn run_eval(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferro-core eval \"<expression>\"");
        return ExitCode::FAILURE;
    }
    let expr = args.join(" ");
    let vars = HashMap::new();
    match evaluate_expression(&expr, &vars) {
        Ok(res) => {
            println!("{}", res);
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("eval error: {}", e);
            ExitCode::FAILURE
        }
    }
}

pub fn run_runner(args: &[String]) -> ExitCode {
    if args.is_empty() || args[0] == "--repl" || args[0] == "-i" {
        return run_repl();
    }

    if args[0] == "eval" || args[0] == "-e" {
        return run_eval(&args[1..]);
    }

    let target_file = &args[0];
    let path = Path::new(target_file);

    if !path.exists() {
        // Fallback: check if the argument is an arithmetic/logic expression
        let candidate_expr = args.join(" ");
        let vars = HashMap::new();
        if let Ok(res) = evaluate_expression(&candidate_expr, &vars) {
            println!("{}", res);
            return ExitCode::SUCCESS;
        }

        eprintln!("ferro-run: cannot find target file '{}'", target_file);
        return ExitCode::FAILURE;
    }

    let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("");

    println!("⚡ [ferro-run] Dispatching execution for '{}' (extension: .{})...", target_file, ext);

    match ext {
        "sh" | "bash" => {
            let status = Command::new("/bin/sh").arg(target_file).args(&args[1..]).status();
            if status.map_or(false, |s| s.success()) { ExitCode::SUCCESS } else { ExitCode::FAILURE }
        }
        "py" => {
            let py_bin = if Path::new("/usr/bin/python3").exists() {
                "/usr/bin/python3"
            } else if Path::new("/bin/python3").exists() {
                "/bin/python3"
            } else {
                "python3"
            };
            let status = Command::new(py_bin).arg(target_file).args(&args[1..]).status();
            if status.map_or(false, |s| s.success()) { ExitCode::SUCCESS } else { ExitCode::FAILURE }
        }
        "c" => {
            // Micro-C compilation to /tmp
            let out_bin = format!("/tmp/.ferro_c_bin_{}", std::process::id());
            let compiler = if Path::new("/usr/bin/gcc").exists() {
                "gcc"
            } else if Path::new("/usr/bin/clang").exists() {
                "clang"
            } else {
                "tcc"
            };

            println!("   • Compiling C source via '{}' -> {}", compiler, out_bin);
            let comp_res = Command::new(compiler)
                .args([target_file, "-O2", "-o", &out_bin])
                .status();

            if comp_res.map_or(false, |s| s.success()) {
                println!("   • Executing compiled binary...");
                let run_res = Command::new(&out_bin).args(&args[1..]).status();
                let _ = fs::remove_file(&out_bin);
                if run_res.map_or(false, |s| s.success()) { ExitCode::SUCCESS } else { ExitCode::FAILURE }
            } else {
                eprintln!("ferro-run: compilation failed via {}", compiler);
                ExitCode::FAILURE
            }
        }
        "rs" => {
            let out_bin = format!("/tmp/.ferro_rs_bin_{}", std::process::id());
            println!("   • Compiling Rust source via rustc -> {}", out_bin);
            let comp_res = Command::new("rustc")
                .args(["-O", target_file, "-o", &out_bin])
                .status();

            if comp_res.map_or(false, |s| s.success()) {
                let run_res = Command::new(&out_bin).args(&args[1..]).status();
                let _ = fs::remove_file(&out_bin);
                if run_res.map_or(false, |s| s.success()) { ExitCode::SUCCESS } else { ExitCode::FAILURE }
            } else {
                eprintln!("ferro-run: rustc compilation failed.");
                ExitCode::FAILURE
            }
        }
        "ferro" | "script" | _ => {
            if let Ok(source) = fs::read_to_string(target_file) {
                let mut engine = MicroScriptEngine::new();
                if let Err(e) = engine.execute(&source) {
                    eprintln!("ferro-run script error: {}", e);
                    return ExitCode::FAILURE;
                }
                ExitCode::SUCCESS
            } else {
                eprintln!("ferro-run: failed to read script '{}'", target_file);
                ExitCode::FAILURE
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_expression_evaluation() {
        let vars = HashMap::new();
        assert_eq!(evaluate_expression("2 + 2", &vars).unwrap(), 4);
        assert_eq!(evaluate_expression("10 * (5 + 3)", &vars).unwrap(), 80);
        assert_eq!(evaluate_expression("0xFF & 0x0F", &vars).unwrap(), 15);
        assert_eq!(evaluate_expression("1 << 10", &vars).unwrap(), 1024);
        assert_eq!(evaluate_expression("100 / 4 - 5", &vars).unwrap(), 20);
    }

    #[test]
    fn test_micro_script_engine() {
        let mut engine = MicroScriptEngine::new();
        let script = r#"
            let a = 10;
            let b = a * 5;
            let msg = "FERRO_TEST_OK";
            let sum = 0;
            let i = 1;
            while i <= 5 {
                sum = sum + i;
                i = i + 1;
            }
            if sum == 15 {
                let success = 1;
            }
            let full = "Status: " + msg;
            let json_doc = "{\"origin\":\"127.0.0.1\",\"agent\":\"ferro\"}";
            let ip = json_get(json_doc, "origin");
        "#;
        engine.execute(script).expect("valid script");
        assert_eq!(engine.vars.get("a"), Some(&10));
        assert_eq!(engine.vars.get("b"), Some(&50));
        assert_eq!(engine.vars.get("sum"), Some(&15));
        assert_eq!(engine.vars.get("success"), Some(&1));
        assert_eq!(engine.string_vars.get("msg"), Some(&"FERRO_TEST_OK".to_string()));
        assert_eq!(engine.string_vars.get("full"), Some(&"Status: FERRO_TEST_OK".to_string()));
        assert_eq!(engine.string_vars.get("ip"), Some(&"127.0.0.1".to_string()));
    }

    #[test]
    fn test_json_get_parser() {
        let sample = r#"{"name": "FerroOS", "version": "2.3.0", "active": true}"#;
        assert_eq!(json_get(sample, "name"), Some("FerroOS".to_string()));
        assert_eq!(json_get(sample, "version"), Some("2.3.0".to_string()));
    }
}
