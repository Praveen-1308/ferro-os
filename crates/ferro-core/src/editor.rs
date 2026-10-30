//! FerroOS Pure-Rust Emergency Recovery Editor (vi & ed)
//!
//! Provides a dependable, self-contained text editor designed for emergency
//! recovery, rescue environments, and minimal container rootfs:
//! - `ed`: Standard POSIX scriptable line editor (supports `p`, `n`, `a`, `i`, `d`, `c`, `w`, `q`, `q!`)
//! - `vi`: Modal full-screen terminal editor with Normal and Insert modes, command line `:` execution,
//!   cursor navigation (`h`/`j`/`k`/`l`, arrows), line deletion (`dd`), undo (`u`), and automatic
//!   non-interactive fallback to line mode.

use std::fs::File;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::Path;
use std::process::ExitCode;

// ============================================================================
// Public Entrypoints: run_ed & run_vi
// ============================================================================

pub fn run_ed(args: &[String]) -> ExitCode {
    if args.iter().any(|a| a == "--help" || a == "-h") {
        println!("Usage: ed [-p PROMPT] [-s] [FILE]");
        println!("Standard POSIX line-oriented text editor in 100% pure Rust.");
        println!("  -p PROMPT  specify command prompt (e.g. -p '*')");
        println!("  -s         suppress byte counts and diagnostics");
        println!("Commands:");
        println!("  p, ,p      print line or all lines");
        println!("  n, ,n      print line(s) with line numbers");
        println!("  a          append text (finish with '.' on its own line)");
        println!("  i          insert text before current line");
        println!("  d          delete current line (or <num>d)");
        println!("  w [FILE]   write buffer to disk");
        println!("  q          quit (warns if modified)");
        println!("  q!         force quit without saving");
        return ExitCode::SUCCESS;
    }

    let mut prompt: Option<String> = None;
    let mut quiet = false;
    let mut file_path: Option<String> = None;

    let mut i = 0;
    let mut parsing_options = true;
    while i < args.len() {
        let arg = &args[i];
        if parsing_options && arg == "--" {
            parsing_options = false;
            i += 1;
            continue;
        }
        if parsing_options && (arg == "-s" || arg == "-") {
            quiet = true;
            i += 1;
        } else if parsing_options && arg == "-p" {
            if i + 1 < args.len() {
                prompt = Some(args[i + 1].clone());
                i += 2;
            } else {
                eprintln!("ed: option requires an argument -- 'p'");
                return ExitCode::from(1);
            }
        } else if parsing_options && arg.starts_with("-p") {
            prompt = Some(arg[2..].to_string());
            i += 1;
        } else if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("ed: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        } else {
            file_path = Some(arg.clone());
            i += 1;
        }
    }

    let mut editor = TextBuffer::new(file_path);
    if let Some(path) = editor.path.clone() {
        if Path::new(&path).exists() {
            match editor.load_file(&path) {
                Ok(bytes) => {
                    if !quiet {
                        println!("{}", bytes);
                    }
                }
                Err(e) => {
                    eprintln!("ed: {}: {}", path, e);
                    return ExitCode::from(1);
                }
            }
        }
    }

    run_ed_loop(&mut editor, prompt.as_deref())
}

pub fn run_vi(args: &[String]) -> ExitCode {
    if args.iter().any(|a| a == "--help" || a == "-h") {
        println!("Usage: vi [FILE]");
        println!("Emergency modal visual screen and recovery editor.");
        println!("Normal Mode Controls:");
        println!("  i, a       enter Insert mode (insert before/after cursor)");
        println!("  o, O       open new line below/above cursor");
        println!("  h, j, k, l move cursor (or arrow keys)");
        println!("  dd         delete current line");
        println!("  x          delete character under cursor");
        println!("  u          undo last deletion");
        println!("  :w [file]  write buffer to disk");
        println!("  :q, :q!    quit / force quit");
        println!("  :wq, ZZ    write and quit");
        return ExitCode::SUCCESS;
    }

    let mut file_path: Option<String> = None;
    let mut parsing_options = true;
    for arg in args {
        if parsing_options && arg == "--" {
            parsing_options = false;
            continue;
        }
        if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("vi: unknown option -- '{}'", arg);
            return ExitCode::from(1);
        }
        if file_path.is_none() {
            file_path = Some(arg.clone());
        }
    }

    let mut editor = TextBuffer::new(file_path.clone());

    if let Some(ref path) = file_path {
        if Path::new(path).exists() {
            if let Err(e) = editor.load_file(path) {
                eprintln!("vi: cannot open {}: {}", path, e);
                return ExitCode::from(1);
            }
        }
    }

    // Check if stdin is an interactive TTY
    let is_tty = is_terminal_interactive();

    if !is_tty {
        // Non-interactive / piped rescue fallback
        return run_ed_loop(&mut editor, None);
    }

    run_vi_terminal(&mut editor)
}

fn is_terminal_interactive() -> bool {
    #[cfg(unix)]
    unsafe {
        libc::isatty(libc::STDIN_FILENO) == 1
    }
    #[cfg(not(unix))]
    false
}

// ============================================================================
// Core TextBuffer Data Structure
// ============================================================================

pub struct TextBuffer {
    pub lines: Vec<String>,
    pub current_line: usize, // 1-based (0 if empty)
    pub cursor_col: usize,   // 0-based
    pub path: Option<String>,
    pub modified: bool,
    pub undo_stack: Vec<(Vec<String>, usize)>,
}

impl TextBuffer {
    pub fn new(path: Option<String>) -> Self {
        Self {
            lines: Vec::new(),
            current_line: 0,
            cursor_col: 0,
            path,
            modified: false,
            undo_stack: Vec::new(),
        }
    }

    pub fn load_file(&mut self, path: &str) -> io::Result<usize> {
        let file = File::open(path)?;
        let reader = BufReader::new(file);
        self.lines.clear();

        let mut total_bytes = 0;
        for line in reader.lines() {
            let l = line?;
            total_bytes += l.len() + 1; // count newline
            self.lines.push(l);
        }

        self.current_line = self.lines.len();
        self.cursor_col = 0;
        self.modified = false;
        Ok(total_bytes)
    }

    pub fn save_file(&mut self, dest: Option<&str>) -> io::Result<usize> {
        let target = dest
            .or(self.path.as_deref())
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "no file name"))?;

        let mut file = File::create(target)?;
        let mut written = 0;

        for line in &self.lines {
            file.write_all(line.as_bytes())?;
            file.write_all(b"\n")?;
            written += line.len() + 1;
        }

        self.modified = false;
        if self.path.is_none() {
            self.path = Some(target.to_string());
        }
        Ok(written)
    }

    pub fn push_undo(&mut self) {
        if self.undo_stack.len() >= 30 {
            self.undo_stack.remove(0);
        }
        self.undo_stack.push((self.lines.clone(), self.current_line));
    }

    pub fn undo(&mut self) -> bool {
        if let Some((prev_lines, prev_cur)) = self.undo_stack.pop() {
            self.lines = prev_lines;
            self.current_line = prev_cur.min(self.lines.len());
            self.modified = true;
            true
        } else {
            false
        }
    }
}

// ============================================================================
// ed Line Editor Engine
// ============================================================================

fn ed_println(msg: &str) -> io::Result<()> {
    let stdout = io::stdout();
    let mut handle = stdout.lock();
    writeln!(handle, "{}", msg)
}

fn run_ed_loop(editor: &mut TextBuffer, prompt: Option<&str>) -> ExitCode {
    macro_rules! ed_out {
        ($($arg:tt)*) => {
            if let Err(e) = ed_println(&format!($($arg)*)) {
                if e.kind() == io::ErrorKind::BrokenPipe {
                    return ExitCode::SUCCESS;
                }
            }
        };
    }

    let stdin = io::stdin();
    let mut reader = stdin.lock();
    let mut input = String::new();
    let mut warn_unsaved = false;

    loop {
        if let Some(p) = prompt {
            print!("{}", p);
            let _ = io::stdout().flush();
        }

        input.clear();
        let bytes_read = match reader.read_line(&mut input) {
            Ok(n) => n,
            Err(_) => break,
        };

        if bytes_read == 0 {
            break;
        }

        let cmd = input.trim_end_matches(&['\r', '\n'][..]).trim();
        if cmd.is_empty() {
            // Enter advances to next line
            if editor.current_line < editor.lines.len() {
                editor.current_line += 1;
                ed_out!("{}", editor.lines[editor.current_line - 1]);
            } else if !editor.lines.is_empty() {
                ed_out!("?");
            }
            continue;
        }

        if cmd == "q" {
            if editor.modified && !warn_unsaved {
                ed_out!("?");
                warn_unsaved = true;
                continue;
            }
            return ExitCode::SUCCESS;
        }

        if cmd == "q!" {
            return ExitCode::SUCCESS;
        }

        warn_unsaved = false;

        if cmd == "p" {
            if editor.current_line > 0 && editor.current_line <= editor.lines.len() {
                ed_out!("{}", editor.lines[editor.current_line - 1]);
            } else {
                ed_out!("?");
            }
            continue;
        }

        if cmd == ",p" || cmd == "1,$p" || cmd == "%p" {
            for line in &editor.lines {
                ed_out!("{}", line);
            }
            if !editor.lines.is_empty() {
                editor.current_line = editor.lines.len();
            }
            continue;
        }

        if cmd == "n" || cmd == ",n" {
            for (idx, line) in editor.lines.iter().enumerate() {
                ed_out!("{}\t{}", idx + 1, line);
            }
            continue;
        }

        if cmd == "a" || cmd.ends_with('a') {
            editor.push_undo();
            let mut insert_idx = if editor.current_line == 0 {
                0
            } else {
                editor.current_line
            };

            let mut appended = Vec::new();
            loop {
                let mut line_in = String::new();
                if reader.read_line(&mut line_in).is_err() || line_in.is_empty() {
                    break;
                }
                let clean = line_in.trim_end_matches(&['\r', '\n'][..]);
                if clean == "." {
                    break;
                }
                appended.push(clean.to_string());
            }

            for line in appended {
                editor.lines.insert(insert_idx, line);
                insert_idx += 1;
            }
            editor.current_line = insert_idx;
            editor.modified = true;
            continue;
        }

        if cmd == "i" {
            editor.push_undo();
            let mut insert_idx = if editor.current_line == 0 {
                0
            } else {
                editor.current_line - 1
            };

            let mut inserted = Vec::new();
            loop {
                let mut line_in = String::new();
                if reader.read_line(&mut line_in).is_err() || line_in.is_empty() {
                    break;
                }
                let clean = line_in.trim_end_matches(&['\r', '\n'][..]);
                if clean == "." {
                    break;
                }
                inserted.push(clean.to_string());
            }

            for line in inserted {
                editor.lines.insert(insert_idx, line);
                insert_idx += 1;
            }
            editor.current_line = insert_idx;
            editor.modified = true;
            continue;
        }

        if cmd == "d" || cmd.ends_with('d') {
            editor.push_undo();
            let target = if cmd == "d" {
                editor.current_line
            } else {
                cmd.trim_end_matches('d').parse::<usize>().unwrap_or(editor.current_line)
            };

            if target > 0 && target <= editor.lines.len() {
                editor.lines.remove(target - 1);
                editor.modified = true;
                editor.current_line = target.min(editor.lines.len());
            } else {
                ed_out!("?");
            }
            continue;
        }

        if cmd.starts_with('w') {
            let dest = cmd.strip_prefix('w').unwrap().trim();
            let save_dest = if dest.is_empty() { None } else { Some(dest) };
            match editor.save_file(save_dest) {
                Ok(bytes) => ed_out!("{}", bytes),
                Err(_) => ed_out!("?"),
            }
            continue;
        }

        if let Ok(line_num) = cmd.parse::<usize>() {
            if line_num > 0 && line_num <= editor.lines.len() {
                editor.current_line = line_num;
                ed_out!("{}", editor.lines[editor.current_line - 1]);
            } else {
                ed_out!("?");
            }
            continue;
        }

        if cmd == "$" {
            if !editor.lines.is_empty() {
                editor.current_line = editor.lines.len();
                ed_out!("{}", editor.lines[editor.current_line - 1]);
            } else {
                ed_out!("?");
            }
            continue;
        }

        ed_out!("?");
    }

    ExitCode::SUCCESS
}

// ============================================================================
// vi Visual Screen Editor (Terminal Raw Mode)
// ============================================================================

#[derive(PartialEq, Eq)]
enum ViMode {
    Normal,
    Insert,
    Command,
}

fn line_char_count(s: &str) -> usize {
    s.chars().count()
}

fn char_to_byte_index(s: &str, char_idx: usize) -> usize {
    s.char_indices().nth(char_idx).map(|(b, _)| b).unwrap_or(s.len())
}

fn remove_char_at(s: &mut String, char_idx: usize) {
    if let Some((byte_pos, c)) = s.char_indices().nth(char_idx) {
        s.drain(byte_pos..byte_pos + c.len_utf8());
    }
}

fn insert_char_at(s: &mut String, char_idx: usize, c: char) {
    let byte_pos = char_to_byte_index(s, char_idx);
    s.insert(byte_pos, c);
}

fn split_line_at(s: &mut String, char_idx: usize) -> String {
    let byte_pos = char_to_byte_index(s, char_idx);
    let rem = s[byte_pos..].to_string();
    s.truncate(byte_pos);
    rem
}

fn run_vi_terminal(editor: &mut TextBuffer) -> ExitCode {
    if editor.lines.is_empty() {
        editor.lines.push(String::new());
        editor.current_line = 1;
    }

    #[cfg(unix)]
    let orig_termios = enable_raw_mode();

    let mut mode = ViMode::Normal;
    let mut command_buf = String::new();
    let mut message = if let Some(ref p) = editor.path {
        format!("\"{}\" {} lines", p, editor.lines.len())
    } else {
        "\"[No Name]\" [New file]".to_string()
    };

    let mut quit = false;
    let exit_code = ExitCode::SUCCESS;

    while !quit {
        render_screen(editor, &mode, &command_buf, &message);
        message.clear();

        let key = read_raw_key();
        match mode {
            ViMode::Normal => match key {
                Key::Char('i') => {
                    editor.push_undo();
                    mode = ViMode::Insert;
                }
                Key::Char('a') => {
                    editor.push_undo();
                    if editor.current_line > 0 {
                        let cur_len = line_char_count(&editor.lines[editor.current_line - 1]);
                        if editor.cursor_col < cur_len {
                            editor.cursor_col += 1;
                        }
                    }
                    mode = ViMode::Insert;
                }
                Key::Char('o') => {
                    editor.push_undo();
                    let idx = editor.current_line;
                    editor.lines.insert(idx, String::new());
                    editor.current_line += 1;
                    editor.cursor_col = 0;
                    editor.modified = true;
                    mode = ViMode::Insert;
                }
                Key::Char('O') => {
                    editor.push_undo();
                    let idx = if editor.current_line > 0 { editor.current_line - 1 } else { 0 };
                    editor.lines.insert(idx, String::new());
                    editor.cursor_col = 0;
                    editor.modified = true;
                    mode = ViMode::Insert;
                }
                Key::Char(':') => {
                    command_buf.clear();
                    mode = ViMode::Command;
                }
                Key::Char('h') | Key::Left => {
                    if editor.cursor_col > 0 {
                        editor.cursor_col -= 1;
                    }
                }
                Key::Char('l') | Key::Right => {
                    if editor.current_line > 0 {
                        let line_len = line_char_count(&editor.lines[editor.current_line - 1]);
                        if editor.cursor_col + 1 < line_len {
                            editor.cursor_col += 1;
                        }
                    }
                }
                Key::Char('k') | Key::Up => {
                    if editor.current_line > 1 {
                        editor.current_line -= 1;
                        clamp_cursor(editor);
                    }
                }
                Key::Char('j') | Key::Down => {
                    if editor.current_line < editor.lines.len() {
                        editor.current_line += 1;
                        clamp_cursor(editor);
                    }
                }
                Key::Char('x') => {
                    if editor.current_line > 0 {
                        let cur_idx = editor.current_line - 1;
                        let len = line_char_count(&editor.lines[cur_idx]);
                        if len > 0 && editor.cursor_col < len {
                            editor.push_undo();
                            remove_char_at(&mut editor.lines[cur_idx], editor.cursor_col);
                            editor.modified = true;
                            clamp_cursor(editor);
                        }
                    }
                }
                Key::Char('d') => {
                    // Check next key for 'dd'
                    let next = read_raw_key();
                    if next == Key::Char('d') {
                        if editor.current_line > 0 && !editor.lines.is_empty() {
                            editor.push_undo();
                            editor.lines.remove(editor.current_line - 1);
                            editor.modified = true;
                            if editor.lines.is_empty() {
                                editor.lines.push(String::new());
                            }
                            if editor.current_line > editor.lines.len() {
                                editor.current_line = editor.lines.len();
                            }
                            clamp_cursor(editor);
                        }
                    }
                }
                Key::Char('u') => {
                    if editor.undo() {
                        message = "1 change undone".to_string();
                    } else {
                        message = "Already at oldest change".to_string();
                    }
                }
                Key::Char('0') => {
                    editor.cursor_col = 0;
                }
                Key::Char('$') => {
                    if editor.current_line > 0 {
                        let len = line_char_count(&editor.lines[editor.current_line - 1]);
                        editor.cursor_col = if len > 0 { len - 1 } else { 0 };
                    }
                }
                Key::Char('G') => {
                    editor.current_line = editor.lines.len();
                    clamp_cursor(editor);
                }
                _ => {}
            },
            ViMode::Insert => match key {
                Key::Esc => {
                    mode = ViMode::Normal;
                    if editor.cursor_col > 0 {
                        editor.cursor_col -= 1;
                    }
                }
                Key::Enter => {
                    if editor.current_line > 0 {
                        let cur_idx = editor.current_line - 1;
                        let remainder = split_line_at(&mut editor.lines[cur_idx], editor.cursor_col);
                        editor.lines.insert(editor.current_line, remainder);
                        editor.current_line += 1;
                        editor.cursor_col = 0;
                        editor.modified = true;
                    }
                }
                Key::Backspace => {
                    if editor.current_line > 0 {
                        let cur_idx = editor.current_line - 1;
                        if editor.cursor_col > 0 {
                            remove_char_at(&mut editor.lines[cur_idx], editor.cursor_col - 1);
                            editor.cursor_col -= 1;
                            editor.modified = true;
                        } else if cur_idx > 0 {
                            let current = editor.lines.remove(cur_idx);
                            editor.current_line -= 1;
                            let prev_len = line_char_count(&editor.lines[editor.current_line - 1]);
                            editor.cursor_col = prev_len;
                            editor.lines[editor.current_line - 1].push_str(&current);
                            editor.modified = true;
                        }
                    }
                }
                Key::Char(c) => {
                    if editor.current_line > 0 {
                        let cur_idx = editor.current_line - 1;
                        let len = line_char_count(&editor.lines[cur_idx]);
                        if editor.cursor_col <= len {
                            insert_char_at(&mut editor.lines[cur_idx], editor.cursor_col, c);
                            editor.cursor_col += 1;
                            editor.modified = true;
                        }
                    }
                }
                _ => {}
            },
            ViMode::Command => match key {
                Key::Esc => {
                    mode = ViMode::Normal;
                    command_buf.clear();
                }
                Key::Enter => {
                    let cmd = command_buf.trim();
                    if cmd == "q" {
                        if editor.modified {
                            message = "No write since last change (add ! to override)".to_string();
                            mode = ViMode::Normal;
                        } else {
                            quit = true;
                        }
                    } else if cmd == "q!" {
                        quit = true;
                    } else if cmd == "w" || cmd.starts_with("w ") {
                        let path_arg = cmd.strip_prefix("w").unwrap().trim();
                        let dest = if path_arg.is_empty() { None } else { Some(path_arg) };
                        match editor.save_file(dest) {
                            Ok(bytes) => {
                                message = format!("\"{}\" {}L, {}B written", editor.path.as_deref().unwrap_or("?"), editor.lines.len(), bytes);
                                mode = ViMode::Normal;
                            }
                            Err(e) => {
                                message = format!("Error writing file: {}", e);
                                mode = ViMode::Normal;
                            }
                        }
                    } else if cmd == "wq" || cmd == "x" {
                        match editor.save_file(None) {
                            Ok(_) => quit = true,
                            Err(e) => {
                                message = format!("Error writing file: {}", e);
                                mode = ViMode::Normal;
                            }
                        }
                    } else {
                        message = format!("Not an editor command: :{}", cmd);
                        mode = ViMode::Normal;
                    }
                    command_buf.clear();
                }
                Key::Backspace => {
                    if command_buf.is_empty() {
                        mode = ViMode::Normal;
                    } else {
                        command_buf.pop();
                    }
                }
                Key::Char(c) => {
                    command_buf.push(c);
                }
                _ => {}
            },
        }
    }

    // Reset terminal screen
    print!("\x1B[2J\x1B[H");
    let _ = io::stdout().flush();

    #[cfg(unix)]
    if let Some(t) = orig_termios {
        disable_raw_mode(&t);
    }

    exit_code
}

fn clamp_cursor(editor: &mut TextBuffer) {
    if editor.current_line > 0 {
        let count = line_char_count(&editor.lines[editor.current_line - 1]);
        if editor.cursor_col >= count && count > 0 {
            editor.cursor_col = count - 1;
        } else if count == 0 {
            editor.cursor_col = 0;
        }
    }
}

fn render_screen(editor: &TextBuffer, mode: &ViMode, cmd_buf: &str, msg: &str) {
    let mut out = String::new();
    // Clear screen and home
    out.push_str("\x1B[H");

    let screen_rows = 24;
    let start_line = if editor.current_line > 18 {
        editor.current_line - 18
    } else {
        1
    };

    for row in 0..screen_rows - 1 {
        let line_idx = start_line + row;
        if line_idx <= editor.lines.len() {
            let l = &editor.lines[line_idx - 1];
            out.push_str("\x1B[K"); // clear to end of line
            out.push_str(l);
        } else {
            out.push_str("\x1B[K~");
        }
        out.push_str("\r\n");
    }

    // Status line
    out.push_str("\x1B[K");
    match mode {
        ViMode::Insert => out.push_str("-- INSERT --"),
        ViMode::Command => out.push_str(&format!(":{}", cmd_buf)),
        ViMode::Normal => {
            if !msg.is_empty() {
                out.push_str(msg);
            } else {
                let p = editor.path.as_deref().unwrap_or("[No Name]");
                out.push_str(&format!("\"{}\" {} lines --{}%--", p, editor.lines.len(), (editor.current_line * 100) / editor.lines.len().max(1)));
            }
        }
    }

    // Position cursor
    let screen_cursor_y = if editor.current_line >= start_line {
        editor.current_line - start_line + 1
    } else {
        1
    };
    let screen_cursor_x = editor.cursor_col + 1;
    out.push_str(&format!("\x1B[{};{}H", screen_cursor_y, screen_cursor_x));

    let mut stdout = io::stdout();
    let _ = stdout.write_all(out.as_bytes());
    let _ = stdout.flush();
}

#[derive(PartialEq, Eq)]
enum Key {
    Char(char),
    Enter,
    Backspace,
    Esc,
    Up,
    Down,
    Left,
    Right,
    Unknown,
}

fn read_raw_key() -> Key {
    let mut stdin = io::stdin();
    let mut buf = [0u8; 4];
    if stdin.read(&mut buf[0..1]).unwrap_or(0) == 0 {
        return Key::Unknown;
    }

    match buf[0] {
        b'\r' | b'\n' => Key::Enter,
        127 | 8 => Key::Backspace,
        0x1B => {
            // ANSI escape sequence
            if stdin.read(&mut buf[1..2]).unwrap_or(0) > 0 && buf[1] == b'[' {
                if stdin.read(&mut buf[2..3]).unwrap_or(0) > 0 {
                    match buf[2] {
                        b'A' => Key::Up,
                        b'B' => Key::Down,
                        b'C' => Key::Right,
                        b'D' => Key::Left,
                        _ => Key::Esc,
                    }
                } else {
                    Key::Esc
                }
            } else {
                Key::Esc
            }
        }
        b if b.is_ascii() => Key::Char(b as char),
        b => {
            let needed = if b & 0xE0 == 0xC0 {
                1
            } else if b & 0xF0 == 0xE0 {
                2
            } else if b & 0xF8 == 0xF0 {
                3
            } else {
                0
            };
            if needed > 0 && stdin.read_exact(&mut buf[1..1 + needed]).is_ok() {
                if let Ok(s) = std::str::from_utf8(&buf[..1 + needed]) {
                    if let Some(c) = s.chars().next() {
                        return Key::Char(c);
                    }
                }
            }
            Key::Unknown
        }
    }
}

#[cfg(unix)]
fn enable_raw_mode() -> Option<libc::termios> {
    unsafe {
        let mut termios: libc::termios = std::mem::zeroed();
        if libc::tcgetattr(libc::STDIN_FILENO, &mut termios) != 0 {
            return None;
        }
        let orig = termios;
        termios.c_lflag &= !(libc::ECHO | libc::ICANON);
        libc::tcsetattr(libc::STDIN_FILENO, libc::TCSAFLUSH, &termios);
        Some(orig)
    }
}

#[cfg(unix)]
fn disable_raw_mode(orig: &libc::termios) {
    unsafe {
        libc::tcsetattr(libc::STDIN_FILENO, libc::TCSAFLUSH, orig);
    }
}

// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;
    use std::fs;

    #[test]
    fn test_text_buffer_save_and_load() {
        let temp_dir = env::temp_dir();
        let target = temp_dir.join("ferro_test_editor_save.txt");
        let path_str = target.to_str().unwrap().to_string();

        let mut buf = TextBuffer::new(Some(path_str.clone()));
        buf.lines.push("alpha".to_string());
        buf.lines.push("beta".to_string());
        buf.save_file(None).expect("must save");

        let mut loader = TextBuffer::new(Some(path_str.clone()));
        let bytes = loader.load_file(&path_str).expect("must load");
        assert_eq!(bytes, 11); // "alpha\n" (6) + "beta\n" (5)
        assert_eq!(loader.lines.len(), 2);
        assert_eq!(loader.lines[0], "alpha");
        assert_eq!(loader.lines[1], "beta");

        let _ = fs::remove_file(&target);
    }

    #[test]
    fn test_text_buffer_undo() {
        let mut buf = TextBuffer::new(None);
        buf.lines.push("first".to_string());

        buf.push_undo();
        buf.lines.push("second".to_string());
        assert_eq!(buf.lines.len(), 2);

        let undone = buf.undo();
        assert!(undone);
        assert_eq!(buf.lines.len(), 1);
        assert_eq!(buf.lines[0], "first");
    }
}
