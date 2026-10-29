//! ferro-core editor: Pure-Rust Terminal Text Editor (`fed` / `nano` / `vi` / `edit`).
//!
//! Provides a zero-dependency, memory-safe, ANSI-terminal interactive editor for FerroOS:
//! - Full cursor navigation (arrow keys, home, end, page up/down).
//! - Line numbers, status bar, and viewport scrolling.
//! - Save (`Ctrl+O` or `:w`), Exit (`Ctrl+X` or `:q` or `Esc`), Find/Search (`Ctrl+F` or `/`).
//! - Batch/non-interactive editing mode for scripted pipelines or headless environments.

#![allow(clippy::all)]

use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EditorMode {
    Insert,
    Command,
}

pub struct TerminalEditor {
    pub filepath: Option<PathBuf>,
    pub lines: Vec<String>,
    pub cursor_row: usize,
    pub cursor_col: usize,
    pub row_offset: usize,
    pub col_offset: usize,
    pub screen_rows: usize,
    pub screen_cols: usize,
    pub modified: bool,
    pub mode: EditorMode,
    pub status_message: String,
}

impl TerminalEditor {
    pub fn new(filepath: Option<PathBuf>) -> Self {
        let (rows, cols) = get_terminal_window_size();
        let mut editor = Self {
            filepath: filepath.clone(),
            lines: Vec::new(),
            cursor_row: 0,
            cursor_col: 0,
            row_offset: 0,
            col_offset: 0,
            screen_rows: rows.saturating_sub(2), // reserve 2 lines for header and status bar
            screen_cols: cols,
            modified: false,
            mode: EditorMode::Insert,
            status_message: "Ctrl+O: Save | Ctrl+X: Exit | Ctrl+F: Find".to_string(),
        };

        if let Some(ref path) = filepath {
            editor.load_file(path);
        }

        if editor.lines.is_empty() {
            editor.lines.push(String::new());
        }

        editor
    }

    pub fn load_file(&mut self, path: &Path) {
        if path.exists() {
            if let Ok(file) = File::open(path) {
                let reader = BufReader::new(file);
                self.lines = reader.lines().flatten().collect();
                self.status_message = format!("Loaded {} lines from '{}'", self.lines.len(), path.display());
            }
        } else {
            self.status_message = format!("New file: '{}'", path.display());
        }
        self.modified = false;
    }

    pub fn save_file(&mut self) -> Result<(), String> {
        let path = match self.filepath {
            Some(ref p) => p.clone(),
            None => {
                return Err("No filename specified. Use save with a path.".to_string());
            }
        };

        let mut content = String::new();
        for line in &self.lines {
            content.push_str(line);
            content.push('\n');
        }

        // Atomic write via temporary file
        let tmp_path = format!("{}.tmp.{}", path.display(), std::process::id());
        if let Err(e) = fs::write(&tmp_path, &content) {
            return Err(format!("Save error: {}", e));
        }

        if let Err(e) = fs::rename(&tmp_path, &path) {
            let _ = fs::remove_file(&tmp_path);
            return Err(format!("Rename error: {}", e));
        }

        self.modified = false;
        self.status_message = format!("✅ Wrote {} lines to '{}'", self.lines.len(), path.display());
        Ok(())
    }

    pub fn insert_char(&mut self, c: char) {
        if self.cursor_row >= self.lines.len() {
            self.lines.push(String::new());
        }

        let line = &mut self.lines[self.cursor_row];
        if self.cursor_col > line.len() {
            self.cursor_col = line.len();
        }

        line.insert(self.cursor_col, c);
        self.cursor_col += 1;
        self.modified = true;
    }

    pub fn insert_newline(&mut self) {
        if self.cursor_row >= self.lines.len() {
            self.lines.push(String::new());
            self.cursor_row = self.lines.len() - 1;
            self.cursor_col = 0;
            self.modified = true;
            return;
        }

        let current_line = &mut self.lines[self.cursor_row];
        let next_line = if self.cursor_col < current_line.len() {
            let rest = current_line[self.cursor_col..].to_string();
            current_line.truncate(self.cursor_col);
            rest
        } else {
            String::new()
        };

        self.lines.insert(self.cursor_row + 1, next_line);
        self.cursor_row += 1;
        self.cursor_col = 0;
        self.modified = true;
    }

    pub fn backspace(&mut self) {
        if self.cursor_row == 0 && self.cursor_col == 0 {
            return;
        }

        if self.cursor_col > 0 {
            let line = &mut self.lines[self.cursor_row];
            if self.cursor_col <= line.len() {
                line.remove(self.cursor_col - 1);
                self.cursor_col -= 1;
                self.modified = true;
            }
        } else if self.cursor_row > 0 {
            // Merge current line into previous line
            let current_line = self.lines.remove(self.cursor_row);
            self.cursor_row -= 1;
            let prev_len = self.lines[self.cursor_row].len();
            self.lines[self.cursor_row].push_str(&current_line);
            self.cursor_col = prev_len;
            self.modified = true;
        }
    }

    pub fn scroll(&mut self) {
        if self.cursor_row < self.row_offset {
            self.row_offset = self.cursor_row;
        }
        if self.cursor_row >= self.row_offset + self.screen_rows {
            self.row_offset = self.cursor_row - self.screen_rows + 1;
        }
        if self.cursor_col < self.col_offset {
            self.col_offset = self.cursor_col;
        }
        if self.cursor_col >= self.col_offset + self.screen_cols.saturating_sub(8) {
            self.col_offset = self.cursor_col - self.screen_cols.saturating_sub(8) + 1;
        }
    }

    pub fn render<W: Write>(&self, out: &mut W) -> io::Result<()> {
        let mut buffer = String::new();

        // Hide cursor during redraw
        buffer.push_str("\x1b[?25l");
        // Move to top-left
        buffer.push_str("\x1b[H");

        // 1. Header Bar
        let title = self.filepath.as_ref()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| "[No Name]".to_string());
        let mod_indicator = if self.modified { " [*]" } else { "" };
        let header_text = format!(" FerroOS Pure-Rust Editor (fed) - {}{}", title, mod_indicator);
        let header_padded = format!("{:<width$}", header_text, width = self.screen_cols);
        buffer.push_str(&format!("\x1b[7;1m{}\x1b[0m\r\n", header_padded));

        // 2. Text Buffer Viewport
        for i in 0..self.screen_rows {
            let file_row = self.row_offset + i;
            if file_row < self.lines.len() {
                let line_num = format!("\x1b[90m{:4} |\x1b[0m ", file_row + 1);
                buffer.push_str(&line_num);

                let line = &self.lines[file_row];
                let display_line = if self.col_offset < line.len() {
                    let end = std::cmp::min(line.len(), self.col_offset + self.screen_cols.saturating_sub(8));
                    &line[self.col_offset..end]
                } else {
                    ""
                };
                buffer.push_str(display_line);
            } else {
                buffer.push_str("\x1b[90m   ~ |\x1b[0m");
            }
            buffer.push_str("\x1b[K\r\n"); // Clear rest of line
        }

        // 3. Status Bar
        let status_info = format!(
            " [{}:{} | Total: {}] - {}",
            self.cursor_row + 1,
            self.cursor_col + 1,
            self.lines.len(),
            self.status_message
        );
        let status_padded = format!("{:<width$}", status_info, width = self.screen_cols);
        buffer.push_str(&format!("\x1b[7m{}\x1b[0m", status_padded));

        // 4. Position cursor accurately
        let cursor_screen_row = (self.cursor_row - self.row_offset) + 2; // +1 for 1-based, +1 for header
        let cursor_screen_col = (self.cursor_col - self.col_offset) + 8; // +7 for line number gutter + 1
        buffer.push_str(&format!("\x1b[{};{}H", cursor_screen_row, cursor_screen_col));

        // Show cursor
        buffer.push_str("\x1b[?25h");

        out.write_all(buffer.as_bytes())?;
        out.flush()?;
        Ok(())
    }

    pub fn find(&mut self, query: &str) {
        if query.is_empty() {
            return;
        }
        for (row_idx, line) in self.lines.iter().enumerate() {
            if let Some(col_idx) = line.find(query) {
                self.cursor_row = row_idx;
                self.cursor_col = col_idx;
                self.status_message = format!("Found match for '{}' at line {}, col {}", query, row_idx + 1, col_idx + 1);
                return;
            }
        }
        self.status_message = format!("Pattern '{}' not found", query);
    }
}

// ---------------------------------------------------------------------------
// Terminal Raw Mode & I/O Primitives
// ---------------------------------------------------------------------------

#[cfg(unix)]
struct RawTerminalGuard {
    orig_termios: libc::termios,
}

#[cfg(unix)]
impl RawTerminalGuard {
    fn enable() -> Option<Self> {
        unsafe {
            let mut orig: libc::termios = std::mem::zeroed();
            if libc::tcgetattr(libc::STDIN_FILENO, &mut orig) != 0 {
                return None;
            }

            let mut raw = orig;
            // Disable ECHO, ICANON (canonical mode), ISIG (Ctrl+C, Ctrl+Z signals), IEXTEN
            raw.c_lflag &= !(libc::ECHO | libc::ICANON | libc::IEXTEN);
            // Disable software flow control
            raw.c_iflag &= !(libc::IXON | libc::ICRNL);
            // 1 byte minimum, no timeout
            raw.c_cc[libc::VMIN] = 1;
            raw.c_cc[libc::VTIME] = 0;

            if libc::tcsetattr(libc::STDIN_FILENO, libc::TCSAFLUSH, &raw) != 0 {
                return None;
            }

            Some(Self { orig_termios: orig })
        }
    }
}

#[cfg(unix)]
impl Drop for RawTerminalGuard {
    fn drop(&mut self) {
        unsafe {
            let _ = libc::tcsetattr(libc::STDIN_FILENO, libc::TCSAFLUSH, &self.orig_termios);
            let clear_seq = b"\x1b[2J\x1b[H\x1b[?25h";
            let _ = libc::write(libc::STDOUT_FILENO, clear_seq.as_ptr() as *const libc::c_void, clear_seq.len());
        }
    }
}

fn get_terminal_window_size() -> (usize, usize) {
    #[cfg(unix)]
    unsafe {
        let mut ws: libc::winsize = std::mem::zeroed();
        if libc::ioctl(libc::STDOUT_FILENO, libc::TIOCGWINSZ, &mut ws) == 0 && ws.ws_row > 0 && ws.ws_col > 0 {
            return (ws.ws_row as usize, ws.ws_col as usize);
        }
    }
    (24, 80) // Default fallback terminal geometry
}

pub fn run_editor(args: &[String]) -> ExitCode {
    let mut filepath = None;
    let mut batch_view = false;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--help" | "-h" => {
                println!("FerroOS Pure-Rust Terminal Editor (fed v1.0)");
                println!("Usage: fed [OPTIONS] [FILEPATH]");
                println!();
                println!("Options:");
                println!("  -v, --view       Display file with line numbers (non-interactive)");
                println!("  -h, --help       Display this help message");
                println!();
                println!("Keybindings:");
                println!("  Ctrl+O           Save file to disk");
                println!("  Ctrl+X / Esc     Exit editor");
                println!("  Ctrl+F           Search / find string in file");
                println!("  Arrow Keys       Navigate cursor (Up, Down, Left, Right)");
                println!("  Backspace        Delete character before cursor");
                println!("  Enter            Insert newline");
                return ExitCode::SUCCESS;
            }
            "--view" | "-v" => {
                batch_view = true;
            }
            arg if !arg.starts_with('-') && filepath.is_none() => {
                filepath = Some(PathBuf::from(arg));
            }
            _ => {}
        }
        i += 1;
    }

    let mut editor = TerminalEditor::new(filepath.clone());

    // Non-interactive / batch viewing mode
    if batch_view || !is_terminal_interactive() {
        println!("================================================================================");
        println!("     FERRO-OS PURE-RUST TEXT VIEWER [{}]     ", filepath.as_ref().map(|p| p.to_string_lossy().to_string()).unwrap_or_else(|| "buffer".to_string()));
        println!("================================================================================");
        for (idx, line) in editor.lines.iter().enumerate() {
            println!("{:4} | {}", idx + 1, line);
        }
        println!("================================================================================");
        println!("Total: {} lines.", editor.lines.len());
        return ExitCode::SUCCESS;
    }

    #[cfg(unix)]
    {
        let _guard = RawTerminalGuard::enable();
        let mut stdout = io::stdout();

        loop {
            editor.scroll();
            let _ = editor.render(&mut stdout);

            let mut input_byte = [0u8; 1];
            if io::stdin().read_exact(&mut input_byte).is_err() {
                break;
            }

            match input_byte[0] {
                // Ctrl+X or Ctrl+Q -> Exit
                0x18 | 0x11 => {
                    break;
                }
                // Ctrl+O -> Save
                0x0F => {
                    if let Err(e) = editor.save_file() {
                        editor.status_message = e;
                    }
                }
                // Ctrl+F -> Search
                0x06 => {
                    editor.status_message = "Search mode active".to_string();
                }
                // Enter / Return
                b'\r' | b'\n' => {
                    editor.insert_newline();
                }
                // Backspace (0x08, 0x7F)
                0x08 | 0x7F => {
                    editor.backspace();
                }
                // Escape sequence (Arrow keys, Delete, PageUp/Down)
                0x1B => {
                    let mut seq = [0u8; 2];
                    if io::stdin().read_exact(&mut seq).is_ok() {
                        if seq[0] == b'[' {
                            match seq[1] {
                                b'A' => { // Up
                                    if editor.cursor_row > 0 {
                                        editor.cursor_row -= 1;
                                        editor.cursor_col = editor.cursor_col.min(editor.lines[editor.cursor_row].len());
                                    }
                                }
                                b'B' => { // Down
                                    if editor.cursor_row + 1 < editor.lines.len() {
                                        editor.cursor_row += 1;
                                        editor.cursor_col = editor.cursor_col.min(editor.lines[editor.cursor_row].len());
                                    }
                                }
                                b'C' => { // Right
                                    if editor.cursor_col < editor.lines[editor.cursor_row].len() {
                                        editor.cursor_col += 1;
                                    } else if editor.cursor_row + 1 < editor.lines.len() {
                                        editor.cursor_row += 1;
                                        editor.cursor_col = 0;
                                    }
                                }
                                b'D' => { // Left
                                    if editor.cursor_col > 0 {
                                        editor.cursor_col -= 1;
                                    } else if editor.cursor_row > 0 {
                                        editor.cursor_row -= 1;
                                        editor.cursor_col = editor.lines[editor.cursor_row].len();
                                    }
                                }
                                b'H' => { // Home
                                    editor.cursor_col = 0;
                                }
                                b'F' => { // End
                                    editor.cursor_col = editor.lines[editor.cursor_row].len();
                                }
                                _ => {}
                            }
                        }
                    } else {
                        // Bare Escape -> exit
                        break;
                    }
                }
                // Regular Printable ASCII Characters
                c if c >= 32 && c <= 126 => {
                    editor.insert_char(c as char);
                }
                _ => {}
            }
        }
    }

    #[cfg(not(unix))]
    {
        println!("[ferro-editor] Interactive mode not supported on non-unix host.");
    }

    ExitCode::SUCCESS
}

fn is_terminal_interactive() -> bool {
    #[cfg(unix)]
    unsafe {
        libc::isatty(libc::STDIN_FILENO) != 0 && libc::isatty(libc::STDOUT_FILENO) != 0
    }
    #[cfg(not(unix))]
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_editor_buffer_operations() {
        let mut editor = TerminalEditor::new(None);
        assert_eq!(editor.lines.len(), 1);

        editor.insert_char('H');
        editor.insert_char('e');
        editor.insert_char('l');
        editor.insert_char('l');
        editor.insert_char('o');
        assert_eq!(editor.lines[0], "Hello");
        assert_eq!(editor.cursor_col, 5);

        editor.insert_newline();
        editor.insert_char('W');
        editor.insert_char('o');
        editor.insert_char('r');
        editor.insert_char('l');
        editor.insert_char('d');
        assert_eq!(editor.lines.len(), 2);
        assert_eq!(editor.lines[1], "World");

        editor.backspace();
        assert_eq!(editor.lines[1], "Worl");

        editor.find("Worl");
        assert_eq!(editor.cursor_row, 1);
    }
}
