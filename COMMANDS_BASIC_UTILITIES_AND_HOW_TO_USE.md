# FerroOS Commands, Basic Utilities & Usage Manual
### *Complete Catalog of Implemented Applets, Practical Playbooks, and Forward Gap Analysis*

FerroOS incorporates [`ferro-core`](file:///Users/praveenkumar/rust%20os/crates/ferro-core/src/main.rs), an ultra-compact, high-performance, multi-call userspace binary written in **100% pure Rust** with zero external C runtime dependencies (`libc = "0.2"`, `flate2 = "1.0"` with safe `miniz_oxide`). Consolidating all traditional GNU coreutils, util-linux, procps, networking binaries, archival engines, modern cloud/container utilities, and cross-platform developer shims into a single **1.3 MB executable**, `ferro-core` provides **218 registered applets** symlinked across `/bin` and `/usr/bin`.

This document tracks every implemented command, its syntax, options, and practical usage, followed by a comprehensive **Gap Analysis** tracking what more is needed for complete parity with enterprise Linux distributions (Ubuntu 24.04 LTS, Debian 12, Alpine 3.20, Windows, and macOS). For a detailed multi-OS comparative audit, refer to [MULTI_OS_COMMANDS_AND_UTILITIES_COMPARATIVE_ANALYSIS.md](file:///Users/praveenkumar/rust%20os/docs/MULTI_OS_COMMANDS_AND_UTILITIES_COMPARATIVE_ANALYSIS.md).

---

## 📑 Table of Contents
1. [Core Architectural Principles](#1-core-architectural-principles)
2. [Category 1: Shell, Execution & Scripting Controls](#2-category-1-shell-execution--scripting-controls)
3. [Category 2: Filesystem, Directory & Storage Management](#3-category-2-filesystem-directory--storage-management)
4. [Category 3: Text & Stream Processing](#4-category-3-text--stream-processing)
5. [Category 4: File Inspection, Hierarchy & Archiving](#5-category-4-file-inspection-hierarchy--archiving)
6. [Category 5: Cryptographic Integrity & Hashing](#6-category-5-cryptographic-integrity--hashing)
7. [Category 6: Process Management & Signal Dispatch](#7-category-6-process-management--signal-dispatch)
8. [Category 7: User Identity, Security & Privileged Access](#8-category-7-user-identity-security--privileged-access)
9. [Category 8: Hardware, Kernel & System Diagnostics](#9-category-8-hardware-kernel--system-diagnostics)
10. [Category 9: Network Diagnostics & Socket Telemetry](#10-category-9-network-diagnostics--socket-telemetry)
11. [Category 10: FerroOS Engine Pillars & Micro-Containers](#11-category-10-ferroos-engine-pillars--micro-containers)
12. [Category 11: Cross-OS Compression, Block I/O & Networking](#12-category-11-cross-os-compression-block-io--networking)
13. [Category 12: Cross-Platform Ergonomics & Developer Shims](#13-category-12-cross-platform-ergonomics--developer-shims)
14. [Category 13: Modern Cloud, Container & Systems Administration](#14-category-13-modern-cloud-container--systems-administration)
15. [Gap Analysis & Roadmap: What More We Need](#15-gap-analysis--roadmap-what-more-we-need)
16. [Verification & Differential Parity Test Suite](#16-verification--differential-parity-test-suite)

---

## 1. Core Architectural Principles

- **Zero-Crash Signal Handling**: Every stream producer (`yes`, `cat`, `strings`, `seq`) implements explicit `EPIPE` / `io::ErrorKind::BrokenPipe` guards, terminating cleanly with exit code `0` when piped to tools like `head -n 5`.
- **Exact Exit Code Conformance**:
  - `0`: Success / True / Process matched.
  - `1`: General failure / False / No process matched (`pgrep`).
  - `2`: Misuse of shell builtins / Missing criteria.
  - `124`: Command timed out ([`timeout`](file:///Users/praveenkumar/rust%20os/crates/ferro-core/src/sys_utils.rs#L396)).
  - `126`: Command invoked cannot execute / Permission denied.
  - `127`: Command or applet not found.
- **In-Process Dispatch Optimization**: The FerroOS shell ([`crates/ferro-core/src/shell.rs`](file:///Users/praveenkumar/rust%20os/crates/ferro-core/src/shell.rs)) executes internal applets directly in-process when unredirected, eliminating `fork()` / `exec()` overhead and yielding microsecond execution times.

---

## 2. Category 1: Shell, Execution & Scripting Controls

### `sh` / `bash`
- **Syntax**: `sh [-c "command string"] [script_file] [args...]`
- **Description**: POSIX-compliant shell supporting variable expansion (`$VAR`, `${VAR}`), conditionals (`if / then / else / fi`), loops (`for i in ...; do ... done`), case pattern matching, exit status `$?`, signal handling, and pipeline redirections (`|`, `>`, `>>`, `<`).
- **Usage Examples**:
  ```bash
  # Execute one-liner script
  sh -c 'for i in 1 2 3; do echo "Pass: $i"; done'

  # Launch interactive shell
  sh
  ```

### `[` / `test`
- **Syntax**: `test EXPRESSION` or `[ EXPRESSION ]`
- **Description**: Evaluates conditional expressions according to POSIX standards. Supports file tests (`-f`, `-d`, `-e`, `-s`, `-r`, `-w`, `-x`), string tests (`-z`, `-n`, `=`, `!=`), and integer comparisons (`-eq`, `-ne`, `-lt`, `-le`, `-gt`, `-ge`).
- **Usage Examples**:
  ```bash
  [ -f /etc/resolv.conf ] && echo "DNS config present"
  [ "$USER" = "root" ] && echo "Running as root"
  ```

### `true` & `false`
- **Syntax**: `true`, `false`, or `:`
- **Description**: Standard null-operation returning exit status `0` (`true`, `:`) or exit status `1` (`false`).
- **Usage Examples**:
  ```bash
  while true; do check_status || break; done
  false || echo "False returned non-zero as expected"
  ```

### `which`
- **Syntax**: `which [-a] PROGRAM...`
- **Description**: Locates executables in the current `$PATH` environment and returns their absolute paths.
- **Usage Examples**:
  ```bash
  which ferro-core
  which ls cat sh
  ```

### `env` & `printenv`
- **Syntax**: `env [NAME=VALUE...] [COMMAND]` or `printenv [VARIABLE]`
- **Description**: Displays all environment variables or runs a specified command in a modified environment. `printenv` prints specific variables or all variables.
- **Usage Examples**:
  ```bash
  printenv PATH
  env PORT=8080 ./server
  ```

### `sleep`
- **Syntax**: `sleep NUMBER[s|m|h|d]`
- **Description**: Suspends execution for the specified duration (supports seconds, minutes, hours, days).
- **Usage Examples**:
  ```bash
  sleep 0.5
  sleep 2s
  ```

### `timeout`
- **Syntax**: `timeout [OPTION] DURATION COMMAND [ARG]...`
- **Description**: Runs a command with a deadline. If the command does not terminate before the duration expires, it sends `SIGTERM` (or `--signal`) and exits with standard exit code **124**.
- **Usage Examples**:
  ```bash
  timeout 5s ping 1.1.1.1
  echo "Exit code: $?" # prints 124 if timed out
  ```

### `nohup`
- **Syntax**: `nohup COMMAND [ARG]...`
- **Description**: Runs a command immune to hangups (`SIGHUP`), redirecting standard output and error to `nohup.out` if writing to a terminal.
- **Usage Examples**:
  ```bash
  nohup ./my_daemon.sh &
  ```

### `watch`
- **Syntax**: `watch [-n SECONDS] COMMAND...`
- **Description**: Executes a command periodically and displays the output full-screen with a terminal header showing the update interval and current time.
- **Usage Examples**:
  ```bash
  watch -n 1 ls -la /tmp
  ```

### `nice` & `renice`
- **Syntax**: `nice [-n ADJUSTMENT] COMMAND...` and `renice [-n] PRIORITY -p PID...`
- **Description**: Adjusts process scheduling priority (niceness) via `libc::getpriority` and `libc::setpriority` (-20 to 19).
- **Usage Examples**:
  ```bash
  nice -n 10 ./heavy_compute_job
  renice -n 5 -p 1234
  ```

### `xargs`
- **Syntax**: `xargs [OPTION]... [COMMAND [INITIAL-ARGS]...]`
- **Description**: Builds and executes command lines from standard input items. Supports `-n <max-args>`, `-I <replace-str>`, `-0` (null-terminated), `-r` (no-run-if-empty), and `-t` (verbose trace).
- **Usage Examples**:
  ```bash
  find . -name "*.log" | xargs rm -f
  printf "1\n2\n3\n" | xargs -n 1 echo "Item:"
  ```

### `chroot`
- **Syntax**: `chroot NEWROOT [COMMAND [ARG]...]`
- **Description**: Runs a command or interactive shell with root directory set to `NEWROOT` via `libc::chroot`.
- **Usage Examples**:
  ```bash
  chroot /mnt/rootfs /bin/sh
  ```

### `clear`
- **Syntax**: `clear`
- **Description**: Clears the terminal screen using ANSI escape sequences (`\x1b[2J\x1b[H`).

---

## 3. Category 2: Filesystem, Directory & Storage Management

### `ls`
- **Syntax**: `ls [-a] [-l] [-h] [-d] [-F] [FILE/DIR...]`
- **Description**: Lists directory contents with permissions, owner, group, file sizes, and modification timestamps.
- **Usage Examples**:
  ```bash
  ls -lah /var/log
  ls -d */
  ```

### `cat`
- **Syntax**: `cat [-n] [-b] [-s] [FILE...]`
- **Description**: Concatenates files and prints them to standard output. Supports line numbering (`-n`) and non-empty line numbering (`-b`).
- **Usage Examples**:
  ```bash
  cat /etc/hostname
  cat file1.txt file2.txt > combined.txt
  ```

### `cp` & `mv`
- **Syntax**: `cp [-r|-R] [-f] [-p] SOURCE... DEST` and `mv [-f] SOURCE... DEST`
- **Description**: Copies or moves files and directories. Uses zero-copy kernel fast-path where available and preserves permissions with `-p`.
- **Usage Examples**:
  ```bash
  cp -r /etc /tmp/etc_backup
  mv /tmp/test.log /tmp/test.log.old
  ```

### `rm` & `rmdir`
- **Syntax**: `rm [-r|-R] [-f] FILE...` and `rmdir DIR...`
- **Description**: Removes files, directories (`-r`), and empty directories (`rmdir`).
- **Usage Examples**:
  ```bash
  rm -rf /tmp/scratch_dir
  rmdir /tmp/empty_dir
  ```

### `mkdir`
- **Syntax**: `mkdir [-p] [-m MODE] DIR...`
- **Description**: Creates directories. `-p` creates intermediate parent directories without error if they already exist.
- **Usage Examples**:
  ```bash
  mkdir -p /var/log/ferro/services
  ```

### `touch`
- **Syntax**: `touch FILE...`
- **Description**: Updates file access and modification timestamps, or creates empty files if they do not exist.
- **Usage Examples**:
  ```bash
  touch /var/run/service.pid
  ```

### `ln`, `link` & `unlink`
- **Syntax**: `ln [-s] [-f] TARGET LINK_NAME`, `link FILE1 FILE2`, `unlink FILE`
- **Description**: Creates symbolic (`-s`) or hard links (`ln`, `link`), and removes a single file link via `unlink`.
- **Usage Examples**:
  ```bash
  ln -s /bin/ferro-core /bin/date
  link original.txt hardlink.txt
  unlink hardlink.txt
  ```

### `chmod` & `chown`
- **Syntax**: `chmod [-R] MODE FILE...` and `chown [-R] USER[:GROUP] FILE...`
- **Description**: Changes file permissions (octal e.g. `0755` or symbolic `u+x,g-w`) and file ownership.
- **Usage Examples**:
  ```bash
  chmod 755 /usr/bin/custom_script
  chmod -R 600 /root/.ssh
  chown -R ferro:ferro /home/ferro
  ```

### `stat`
- **Syntax**: `stat FILE...`
- **Description**: Displays detailed filesystem status: size, blocks, I/O block, inode, device, links, permissions, UID, GID, atime, mtime, and ctime.
- **Usage Examples**:
  ```bash
  stat /etc/passwd
  ```

### `mktemp`
- **Syntax**: `mktemp [-d] [-u] [-p DIR] [TEMPLATE]`
- **Description**: Creates temporary files (mode `0600`) or directories (`-d`, mode `0700`) using atomic `O_CREAT | O_EXCL` flags, mitigating CWE-377 insecure temporary file creation vulnerabilities.
- **Usage Examples**:
  ```bash
  TEMP_FILE=$(mktemp)
  TEMP_DIR=$(mktemp -d /tmp/build.XXXXXX)
  ```

### `readlink` & `realpath`
- **Syntax**: `readlink [-f] FILE...` and `realpath FILE...`
- **Description**: Resolves symbolic link targets and canonicalizes pathnames, expanding relative components (`.` and `..`).
- **Usage Examples**:
  ```bash
  readlink /bin/sh
  realpath ../crates/ferro-core
  ```

### `basename` & `dirname`
- **Syntax**: `basename PATH [SUFFIX]` and `dirname PATH`
- **Description**: Standard POSIX path component extraction and suffix removal.
- **Usage Examples**:
  ```bash
  basename /var/log/syslog.1.gz .gz   # returns "syslog.1"
  dirname /etc/nginx/nginx.conf        # returns "/etc/nginx"
  ```

### `truncate`
- **Syntax**: `truncate -s SIZE [-c] FILE...`
- **Description**: Shrinks or extends the size of each file to the specified size (supports `K`, `M`, `G` and relative `+N` / `-N`).
- **Usage Examples**:
  ```bash
  truncate -s 10M /tmp/sparse_test.img
  truncate -s +1K /tmp/grow.bin
  ```

### `split`
- **Syntax**: `split [-b BYTES] [-l LINES] [-d] [-a LEN] [INPUT [PREFIX]]`
- **Description**: Segments a file into fixed-size byte chunks or line counts with numeric (`-d`) or alphabetic suffixes.
- **Usage Examples**:
  ```bash
  split -b 50M -d backup.tar.gz backup.part_
  split -l 1000 access.log log_chunk_
  ```

### `du` & `df`
- **Syntax**: `du [-s] [-h] [-a] [PATH...]` and `df [-h] [PATH...]`
- **Description**: Summarizes disk usage for directories/files in standard POSIX 1K blocks or human-readable units (`-h`), and inspects filesystem free space via `statvfs`.
- **Usage Examples**:
  ```bash
  du -sh /var/cache
  df -h /
  ```

### `sync`
- **Syntax**: `sync`
- **Description**: Flushes dirty filesystem buffers to physical backing media via `libc::sync`.

---

## 4. Category 3: Text & Stream Processing

### `grep`
- **Syntax**: `grep [-i] [-v] [-c] [-l] [-n] PATTERN [FILE...]`
- **Description**: Searches for patterns across text files or standard input with case-insensitive matching (`-i`), inverted matching (`-v`), match counts (`-c`), and line numbers (`-n`).
- **Usage Examples**:
  ```bash
  grep -i "error" /var/log/syslog
  ps | grep -v "kworker"
  ```

### `find`
- **Syntax**: `find [PATH] [-name PATTERN] [-type f|d|l] [-maxdepth N] [-exec CMD {} +]`
- **Description**: Recursively descends directory trees to locate files matching names, types, or depths.
- **Usage Examples**:
  ```bash
  find /var/log -name "*.log" -type f
  find . -maxdepth 2 -type d
  ```

### `head` & `tail`
- **Syntax**: `head [-n LINES] [-c BYTES] [FILE...]` and `tail [-n LINES] [FILE...]`
- **Description**: Outputs the first or last $N$ lines of input streams (default 10 lines).
- **Usage Examples**:
  ```bash
  head -n 20 /etc/services
  tail -n 50 /var/log/messages
  ```

### `wc`
- **Syntax**: `wc [-l] [-w] [-c] [-m] [FILE...]`
- **Description**: Counts newline lines (`-l`), words (`-w`), and byte counts (`-c`).
- **Usage Examples**:
  ```bash
  wc -l /etc/passwd
  cat log.txt | wc -w
  ```

### `tee`
- **Syntax**: `tee [-a] FILE...`
- **Description**: Copies standard input to standard output and to one or more files simultaneously (`-a` appends).
- **Usage Examples**:
  ```bash
  ./build.sh | tee /tmp/build.log
  ```

### `echo` & `printf`
- **Syntax**: `echo [-n] [-e] [STRING...]` and `printf FORMAT [ARG...]`
- **Description**: Prints arguments with escape sequence expansion (`\n`, `\t`, `\xHH`) and standard format specifiers (`%s`, `%d`, `%x`).
- **Usage Examples**:
  ```bash
  echo -e "Line 1\nLine 2"
  printf "User: %-15s PID: %05d\n" "root" 1
  ```

### `cut`
- **Syntax**: `cut [-d DELIM] [-f FIELDS] [-c CHARS] [FILE...]`
- **Description**: Extracts sections from lines by delimiter-separated fields (`-f 1,3`) or character positions (`-c 1-10`).
- **Usage Examples**:
  ```bash
  cut -d ":" -f 1,7 /etc/passwd
  cut -c 1-8 /proc/version
  ```

### `sort` & `uniq`
- **Syntax**: `sort [-n] [-r] [-u] [-k FIELD] [FILE...]` and `uniq [-c] [-d] [-u] [FILE...]`
- **Description**: Sorts text lines lexicographically or numerically (`-n`), reverses sort order (`-r`), and filters adjacent duplicate lines (`uniq -c` counts frequency).
- **Usage Examples**:
  ```bash
  cat /etc/passwd | cut -d: -f7 | sort | uniq -c
  sort -n -r scores.txt
  ```

### `tr`
- **Syntax**: `tr [-d] [-s] SET1 [SET2]`
- **Description**: Translates, squeezes repeats (`-s`), or deletes (`-d`) characters from standard input. Supports character classes (`[:upper:]`, `[:lower:]`, `[:digit:]`).
- **Usage Examples**:
  ```bash
  cat file.txt | tr '[:lower:]' '[:upper:]'
  cat file.txt | tr -d '\r'
  ```

### `yes` & `seq`
- **Syntax**: `yes [STRING]` and `seq [FIRST] [INCREMENT] LAST`
- **Description**: Continuously emits strings (with `EPIPE` safety) or generates numeric sequences.
- **Usage Examples**:
  ```bash
  yes y | ./interactive_installer.sh
  seq 1 2 10
  ```

### `base64`
- **Syntax**: `base64 [-d] [-w COLS] [FILE]`
- **Description**: Encodes or decodes (`-d`) RFC 4648 base64 data.
- **Usage Examples**:
  ```bash
  echo -n "FerroOS" | base64
  echo "RmVycm9PUw==" | base64 -d
  ```

### `sed`
- **Syntax**: `sed [-i] [-n] 's/pattern/replacement/flags' [FILE...]`
- **Description**: Stream editor supporting regular expression substitutions (`s///g`), case-insensitive replacement (`i`), print filtering (`-n 'p'`), line deletion (`d`), and atomic in-place file modifications (`-i`).
- **Usage Examples**:
  ```bash
  sed 's/localhost/127.0.0.1/g' config.txt
  sed -i 's/DEBUG=true/DEBUG=false/g' /etc/app.conf
  ```

### `diff` & `cmp`
- **Syntax**: `diff [-u] FILE1 FILE2` and `cmp FILE1 FILE2`
- **Description**: Computes unified line-by-line diffs (`-u`) or byte-by-byte comparisons (`cmp`).
- **Usage Examples**:
  ```bash
  diff -u config.orig config.new
  cmp binary_v1.bin binary_v2.bin
  ```

### `comm`
- **Syntax**: `comm [-1] [-2] [-3] FILE1 FILE2`
- **Description**: Compares two sorted files line by line, generating 3 distinct columns: lines unique to FILE1, lines unique to FILE2, and lines common to both.
- **Usage Examples**:
  ```bash
  comm -12 sorted_list1.txt sorted_list2.txt   # print only common lines
  ```

### `tac` & `rev`
- **Syntax**: `tac [FILE...]` and `rev [FILE...]`
- **Description**: Reverses lines from end to start (`tac`), or reverses characters horizontally within each line (`rev`).
- **Usage Examples**:
  ```bash
  tac /var/log/syslog | head -n 20   # read newest lines first
  echo "hello world" | rev            # prints "dlrow olleh"
  ```

### `nl`
- **Syntax**: `nl [-ba|-bt] [-s SEP] [-w WIDTH] [FILE...]`
- **Description**: Formats and numbers lines in a text file.
- **Usage Examples**:
  ```bash
  nl -s ": " source_code.rs
  ```

### `paste`
- **Syntax**: `paste [-d DELIM] [-s] [FILE...]`
- **Description**: Merges lines from multiple files horizontally with delimiters, or serializes lines into a single delimited line (`-s`).
- **Usage Examples**:
  ```bash
  paste -d "," names.txt emails.txt
  seq 1 5 | paste -s -d "+" -
  ```

### `fold`
- **Syntax**: `fold [-w WIDTH] [-s] [FILE...]`
- **Description**: Wraps lines of text to fit a specified column width (default 80 columns).
- **Usage Examples**:
  ```bash
  fold -w 60 long_paragraph.txt
  ```

### `xxd` & `hexdump`
- **Syntax**: `xxd [-p] [-r] [-c COLS] [FILE]` and `hexdump [-C] [FILE...]`
- **Description**: Generates canonical hexadecimal dumps with ASCII sidebars, or converts hex representations back into raw binary files (`xxd -r`).
- **Usage Examples**:
  ```bash
  xxd -c 16 /bin/sh | head -n 5
  printf "hello" | xxd | xxd -r   # byte-exact roundtrip
  ```

### `shuf`
- **Syntax**: `shuf [-i LO-HI] [-n COUNT] [-e STRING...] [FILE]`
- **Description**: Generates random permutations of input lines or integers via Fisher-Yates shuffle.
- **Usage Examples**:
  ```bash
  shuf -i 1-100 -n 5
  cat candidates.txt | shuf
  ```

### `strings`
- **Syntax**: `strings [-n MIN_LEN] [-t x|o|d] [FILE...]`
- **Description**: Scans binary files for continuous sequences of printable ASCII/UTF-8 characters.
- **Usage Examples**:
  ```bash
  strings -n 8 /bin/ferro-core | head -n 20
  strings -t x library.so | grep "GLIBC"
  ```

---

## 5. Category 4: File Inspection, Hierarchy & Archiving

### `file`
- **Syntax**: `file [-b] [-i] FILE...`
- **Description**: Determines file classification by inspecting filesystem metadata and magic byte headers.
  - **Identifies**: ELF 32/64-bit binaries (x86_64, aarch64, RISC-V), Mach-O, Windows PE/MZ, Gzip, Tar, Zip, Bzip2, XZ, Zstd, PNG, JPEG, GIF, PDF, shell scripts (`#!`), JSON data, ASCII text, UTF-8 text, directories, sockets, FIFOs, and devices.
  - Supports `-b` (brief mode, suppresses filename) and `-i` (MIME type string).
- **Usage Examples**:
  ```bash
  file /bin/sh                    # prints: /bin/sh: ELF 64-bit LSB executable, ...
  file -i document.pdf            # prints: document.pdf: application/pdf
  ```

### `tree`
- **Syntax**: `tree [-L LEVEL] [-a] [-d] [-s] [-h] [DIR]`
- **Description**: Recursively visualizes directory structure with Unicode box-drawing characters (`├── `, `└── `, `│   `). Reports file counts, directory counts, and file sizes.
- **Usage Examples**:
  ```bash
  tree -L 2 /etc
  tree -d /usr
  ```

### `tar`
- **Syntax**: `tar -c|-x|-t [-v] [-f ARCHIVE] [-C DIR] [FILES...]`
- **Description**: Pure-Rust POSIX `ustar` archive creator (`-c`), extractor (`-x`), and content lister (`-t`). Preserves file permissions, 512-byte block boundaries, and supports combined flags (`tar -cvf`, `tar xvf`).
- **Usage Examples**:
  ```bash
  tar -cvf backup.tar /etc /var/log
  tar -tvf backup.tar
  tar -xvf backup.tar -C /tmp/restore
  ```

---

## 6. Category 5: Cryptographic Integrity & Hashing

### `sha256sum`, `md5sum` & `sha1sum`
- **Syntax**: `sha256sum [-c] [FILE...]`, `md5sum [-c] [FILE...]`, `sha1sum [-c] [FILE...]`
- **Description**: Computes cryptographic message digests according to FIPS 180-4 (SHA-256), RFC 1321 (MD5), and FIPS 180-1 (SHA-1). Supports check mode (`-c`, `--check`) to verify existing digest files with standard Linux exit codes.
- **Usage Examples**:
  ```bash
  # Calculate checksums
  sha256sum package.rpk > package.rpk.sha256
  md5sum archive.tar

  # Verify checksums
  sha256sum -c package.rpk.sha256   # prints: package.rpk: OK
  ```

---

## 7. Category 6: Process Management & Signal Dispatch

### `ps`
- **Syntax**: `ps [-e] [-f] [-o FORMAT]`
- **Description**: Lists running processes by reading Linux `/proc/[pid]/` status, comm, and cmdline files. Displays PID, TTY, CPU time, and command name.
- **Usage Examples**:
  ```bash
  ps
  ps -ef
  ```

### `kill`
- **Syntax**: `kill [-s SIGNAL | -SIGNAL] PID...`
- **Description**: Sends signals (`SIGTERM` 15, `SIGKILL` 9, `SIGHUP` 1, `SIGINT` 2) to specified process IDs via `libc::kill`.
- **Usage Examples**:
  ```bash
  kill 1234
  kill -9 9876
  ```

### `pgrep`, `pkill` & `killall`
- **Syntax**: `pgrep [-f] [-x] [-l] PATTERN`, `pkill [-f] [-x] [-SIGNAL] PATTERN`, `killall [-v] [-SIGNAL] NAME...`
- **Description**: Looks up or signals processes based on name or command line (`-f`). Returns exit code `0` if at least one process was matched, and `1` if no processes were found.
- **Usage Examples**:
  ```bash
  pgrep -l nginx
  pkill -HUP ferro-service
  killall -v worker_process
  ```

### `uptime`
- **Syntax**: `uptime`
- **Description**: Displays current system wall-clock time, system uptime, active user count, and 1, 5, and 15-minute load averages from `/proc/loadavg` and `/proc/uptime`.

---

## 8. Category 7: User Identity, Security & Privileged Access

### `whoami` & `id`
- **Syntax**: `whoami` and `id [-u] [-g] [-G] [-n] [USER]`
- **Description**: Prints active effective username, UID, primary GID, and supplementary groups.
- **Usage Examples**:
  ```bash
  whoami
  id ferro
  ```

### `groups` & `logname`
- **Syntax**: `groups [USER...]` and `logname`
- **Description**: Resolves group memberships for one or more users, or prints the initial login session name.
- **Usage Examples**:
  ```bash
  groups
  groups ferro root
  logname
  ```

### `sudo` & `su`
- **Syntax**: `sudo [-u USER] COMMAND...` and `su [-] [USER]`
- **Description**: Executes commands with superuser privileges or switches the current session user. Validates permissions against `/etc/sudoers` and shadow authentication.
- **Usage Examples**:
  ```bash
  sudo systemctl restart ferro-superd
  su - ferro
  ```

### `sandbox` (Landlock LSM)
- **Syntax**: `sandbox --ro /path --rw /path COMMAND...`
- **Description**: Enforces kernel-level Landlock LSM sandboxing around unprivileged processes, restricting filesystem reads and writes to authorized paths.
- **Usage Examples**:
  ```bash
  sandbox --ro /usr --rw /tmp /bin/sh
  ```

---

## 9. Category 8: Hardware, Kernel & System Diagnostics

### `uname`
- **Syntax**: `uname [-a] [-s] [-n] [-r] [-m]`
- **Description**: Prints system and kernel information (`-a` prints kernel name, network nodename, release, architecture, and OS).
- **Usage Examples**:
  ```bash
  uname -a
  ```

### `hostname`
- **Syntax**: `hostname [NEW_HOSTNAME]`
- **Description**: Displays or configures the system hostname stored in `/etc/hostname`.
- **Usage Examples**:
  ```bash
  hostname
  hostname ferro-node-01
  ```

### `nproc` & `lscpu`
- **Syntax**: `nproc` and `lscpu`
- **Description**: Gathers CPU topology, active core counts, cache sizes, CPU flags (SSE, AVX, NEON), and architecture details from `/proc/cpuinfo`.
- **Usage Examples**:
  ```bash
  nproc
  lscpu | grep "Model name"
  ```

### `lsmod` & `lspci`
- **Syntax**: `lsmod` and `lspci`
- **Description**: Inspects loaded Linux kernel modules (`/proc/modules`) and enumerates PCI bus controllers and devices (`/sys/bus/pci/devices`).
- **Usage Examples**:
  ```bash
  lsmod
  lspci
  ```

### `sysctl`
- **Syntax**: `sysctl [-w KEY=VALUE] [KEY...]`
- **Description**: Reads or modifies runtime Linux kernel tuning parameters located in `/proc/sys/`.
- **Usage Examples**:
  ```bash
  sysctl net.ipv4.ip_forward
  sysctl -w vm.max_map_count=262144
  ```

### `lsblk` & `blkid`
- **Syntax**: `lsblk` and `blkid [DEVICE...]`
- **Description**: Discovers block devices, partitions, filesystem types (ext4, btrfs, vfat), and UUID labels.
- **Usage Examples**:
  ```bash
  lsblk
  blkid /dev/sda1
  ```

### `free`
- **Syntax**: `free [-m] [-g] [-h]`
- **Description**: Displays total, used, free, and available memory from `/proc/meminfo`.
- **Usage Examples**:
  ```bash
  free -m
  ```

### `dmesg`
- **Syntax**: `dmesg [-c]`
- **Description**: Reads and prints kernel ring-buffer messages via `/dev/kmsg` or `/proc/kmsg`.

### `cal`
- **Syntax**: `cal [MONTH] [YEAR]`
- **Description**: Displays a formatted 7-column Gregorian calendar for the current or specified month/year, highlighting today's date.
- **Usage Examples**:
  ```bash
  cal
  cal 12 2026
  ```

### `date`
- **Syntax**: `date [-u] [+FORMAT]`
- **Description**: Prints wall-clock time in POSIX format (`+%s`, `+%Y-%m-%d`, `+%T`). Supports UTC (`-u`).
- **Usage Examples**:
  ```bash
  date "+%Y-%m-%d %H:%M:%S"
  date -u +%s
  ```

### `factor`
- **Syntax**: `factor [NUMBER...]`
- **Description**: Computes prime factorization of specified positive integers.
- **Usage Examples**:
  ```bash
  factor 42 100 1234567   # prints: 42: 2 3 7, 100: 2 2 5 5, 1234567: 127 9721
  ```

### `reboot` & `poweroff`
- **Syntax**: `reboot` and `poweroff`
- **Description**: Sends kernel reboot or poweroff system calls (`LINUX_REBOOT_CMD_RESTART`, `LINUX_REBOOT_CMD_POWER_OFF`).

---

## 10. Category 9: Network Diagnostics & Socket Telemetry

### `ifconfig` & `ip`
- **Syntax**: `ifconfig [IFACE]` and `ip link|addr|route show`
- **Description**: Inspects network interface operational state, MTU, IPv4 address, netmask, broadcast, IPv6 link-local, MAC address, and RX/TX packet statistics.
- **Usage Examples**:
  ```bash
  ifconfig eth0
  ip addr show
  ```

### `netstat` & `ss`
- **Syntax**: `netstat [-t] [-u] [-l] [-n]` and `ss [-t] [-u] [-l] [-n]`
- **Description**: Displays listening and established TCP/UDP sockets by reading `/proc/net/tcp` and `/proc/net/udp`.
- **Usage Examples**:
  ```bash
  ss -tlnp
  netstat -tlpn
  ```

### `ping`
- **Syntax**: `ping [-c COUNT] [-W TIMEOUT] HOST`
- **Description**: Performs network reachability diagnostics, sending ICMP echo requests or TCP socket round-trip probes and computing minimum, average, and maximum latencies.
- **Usage Examples**:
  ```bash
  ping -c 4 1.1.1.1
  ```

### `wget` & `curl` / `fetch`
- **Syntax**: `wget [-O OUTPUT] URL` and `curl [-s] [-o OUTPUT] URL`
- **Description**: Downloads files and queries HTTP/HTTPS REST APIs.
- **Usage Examples**:
  ```bash
  wget -O /tmp/data.json http://127.0.0.1:8080/api/status
  curl http://localhost:8080/metrics
  ```

### `dhcp` / `udhcpc`
- **Syntax**: `dhcp [IFACE]`
- **Description**: Client for automatic IPv4 address configuration via DHCP.

---

## 11. Category 10: FerroOS Engine Pillars & Micro-Containers

### `container` / `ferrocage`
- **Syntax**: `ferrocage run|ps|inspect|stop|rm [OPTIONS]`
- **Description**: Ultra-lightweight micro-container engine utilizing Linux cgroups v2, pivot_root, and namespaces.
- **Usage Examples**:
  ```bash
  ferrocage run -d --name test-box --memory 64M /bin/sh
  ferrocage ps
  ferrocage stop test-box
  ```

### `service` / `supervise`
- **Syntax**: `ferro service list|status|start|stop|restart|logs [SERVICE]`
- **Description**: Process supervisor and service manager managing daemons, auto-restart policies, health probes, and ring-buffer log collection.
- **Usage Examples**:
  ```bash
  ferro service status
  ferro service restart qa-worker
  ```

### `disk`
- **Syntax**: `ferro disk list|benchmark|smart`
- **Description**: Inspects disk storage geometry, partitions, and measures direct unbuffered disk write/read throughput.

### `cloud-init`
- **Syntax**: `cloud-init init`
- **Description**: Cloud bootstrapping engine reading `#cloud-config` YAML to provision SSH keys, create users, configure networking, and run initial deployment scripts.

### `rpk` / `ferro-pkg`
- **Syntax**: `rpk install|remove|search|list|profile [PACKAGE]`
- **Description**: Transactional package manager supporting atomic rollbacks, multi-architecture dependency checking, and legacy MSZ/CAB/MSI package parsing.

---

## 12. Category 11: Cross-OS Compression, Block I/O & Networking

### `gzip`, `gunzip` & `zcat`
- **Syntax**: 
  - `gzip [-c] [-d] [-f] [-k] [-1..-9] [FILE...]`
  - `gunzip [-c] [-f] [-k] [FILE.gz...]`
  - `zcat [FILE.gz...]`
- **Description**: RFC 1952 DEFLATE stream compression and decompression in 100% pure Rust. `gzip` replaces files with `.gz` variants (or writes to stdout with `-c`). `zcat` streams decompressed bytes directly to stdout without intermediate temporary disk files.
- **Usage Examples**:
  ```bash
  # Compress log file
  gzip -9 /var/log/syslog

  # Decompress without deleting original
  gunzip -k /var/log/syslog.gz

  # Inspect compressed log in real-time
  zcat /var/log/syslog.gz | grep "ERROR"
  ```

### `dd`
- **Syntax**: `dd [if=FILE] [of=FILE] [bs=BYTES] [count=N] [skip=N] [seek=N] [conv=fsync] [status=none]`
- **Description**: Standard block-level data duplication and stream transfer utility. Supports custom block sizes (`bs=512`, `bs=4k`, `bs=1M`), block skipping, seeking, fsync flushing, and quiet execution.
- **Usage Examples**:
  ```bash
  # Create 64 MB zero-filled disk image
  dd if=/dev/zero of=/var/disks/swap.img bs=1M count=64 conv=fsync

  # Benchmark unbuffered disk block write
  dd if=/dev/zero of=/tmp/bench.bin bs=1M count=100 conv=fsync
  ```

### `mknod` & `mkfifo`
- **Syntax**: 
  - `mknod [-m MODE] NAME TYPE [MAJOR MINOR]`
  - `mkfifo [-m MODE] NAME...`
- **Description**: Creates special device nodes (block `b`, character `c`, or FIFO `p`) or POSIX named FIFO pipes via direct kernel system calls.
- **Usage Examples**:
  ```bash
  # Create named pipe for IPC
  mkfifo /tmp/log_pipe

  # Create character device node
  mknod /dev/null_test c 1 3
  ```

### `time`
- **Syntax**: `time [-p] [-v] COMMAND [ARGS...]`
- **Description**: High-resolution execution timer and resource profiler. Outputs standard POSIX 3-line format (`real`, `user`, `sys` time) with `-p`, and reports peak RSS and page faults with `-v`.
- **Usage Examples**:
  ```bash
  time -p ferro-core printf "profiling execution\n"
  time -v rpk search postgres
  ```

### `pidof`
- **Syntax**: `pidof [-s] NAME...`
- **Description**: Locates the process IDs of running programs by matching their executable name. Supports `-s` for single-shot output.
- **Usage Examples**:
  ```bash
  pidof ferro-superd
  pidof -s sshd
  ```

### `flock`
- **Syntax**: `flock [-s] [-x] [-n] [-u] FILE COMMAND [ARGS...]`
- **Description**: Manages kernel advisory file locks from shell scripts, preventing race conditions across concurrent container jobs or build tasks.
- **Usage Examples**:
  ```bash
  flock /tmp/build.lock make -j4
  flock -n /var/run/cron.lock /usr/bin/backup-job
  ```

### `nc` / `netcat`
- **Syntax**: `nc [-l] [-p PORT] [-w TIMEOUT] [-z] [HOST] [PORT]`
- **Description**: Versatile networking tool for TCP connection probing (`-z`), listening servers (`-l`), and bidirectional payload streaming.
- **Usage Examples**:
  ```bash
  # Port readiness probe (health check)
  nc -z 127.0.0.1 8080 && echo "Service online"

  # Lightweight listener
  nc -l -p 9000
  ```

### `route`
- **Syntax**: `route [-n]`
- **Description**: Displays the kernel IP routing table (`Destination`, `Gateway`, `Genmask`, `Flags`, `Metric`, `Ref`, `Iface`) conforming to standard net-tools format.
- **Usage Examples**:
  ```bash
  route -n
  ```

### `printf`
- **Syntax**: `printf FORMAT [ARG...]`
- **Description**: Pure-Rust formatted output utility supporting `%s`, `%d`, `%i`, `%u`, `%x`, `%f`, and standard escape sequences (`\n`, `\t`, `\r`, `\\`).
- **Usage Examples**:
  ```bash
  printf "Node: %s | CPU Usage: %d%%\n" "prod-01" 42
  ```

### `rmdir`
- **Syntax**: `rmdir [-p] DIRECTORY...`
- **Description**: Removes empty directories from the filesystem, optionally removing parent directories along the specified path with `-p`.
- **Usage Examples**:
  ```bash
  rmdir /tmp/scratch_dir
  rmdir -p /var/log/apps/legacy
  ```

---

## 13. Category 12: Cross-Platform Ergonomics & Developer Shims

FerroOS eliminates developer cognitive friction by providing non-colliding native applets and shims for Windows and macOS reflexes:

### `cls`
- **Syntax**: `cls`
- **Description**: Clears the terminal screen by issuing the ANSI clear sequence `\x1B[2J\x1B[H`. Directly fulfills Windows developer muscle memory.

### `tasklist`
- **Syntax**: `tasklist`
- **Description**: Displays running processes in authentic Windows CMD 4-column tabular format (`Image Name`, `PID`, `Session Name`, `Mem Usage`).

### `taskkill`
- **Syntax**: `taskkill [/f] [/im IMAGE_NAME] [/pid PID]`
- **Description**: Terminates processes using Windows command flags (`/f` for forceful SIGKILL, `/im` for process name matching, `/pid` for numeric ID).

### `ipconfig`
- **Syntax**: `ipconfig [/all] [/flushdns]`
- **Description**: Displays IP configuration for all network interfaces. Supports `/flushdns` to clear FerroOS's local in-memory DNS cache.

### `where`
- **Syntax**: `where PROGRAM...`
- **Description**: Resolves executable paths across `$PATH`, matching Windows CMD `where.exe` behavior without needing `which`.

### `pbcopy` & `clip`
- **Syntax**: `pbcopy` or `clip`
- **Description**: Copies standard input into the terminal clipboard buffer using OSC 52 ANSI escape sequences.

### `pbpaste`
- **Syntax**: `pbpaste`
- **Description**: Pastes clipboard contents directly to standard output.

### `open` & `start`
- **Syntax**: `open [FILE|URL]` or `start [FILE|URL]`
- **Description**: Universal desktop launcher delegating to default file handlers or browsers.

---

## 14. Category 13: Modern Cloud, Container & Systems Administration

FerroOS incorporates modern utilities specifically addressing areas where DevOps practitioners, container builders, and systems engineers struggle on minimal distributions:

### `envsubst`
- **Syntax**: `envsubst [SHELL-FORMAT] [FILE]`
- **Description**: Substitutes environment variable values into templates. Supports `${VAR}` and `$VAR`. When `SHELL-FORMAT` is specified (e.g. `'$PORT,$HOST'`), only the named variables are substituted, leaving other expressions untouched.
- **Usage Examples**:
  ```bash
  # Standard template rendering in container entrypoint
  envsubst < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

  # Filtered substitution
  envsubst '$API_URL,$PORT' < config.template.json > config.json
  ```

### `uuidgen` / `uuid`
- **Syntax**: `uuidgen [-r] [-t] [-n COUNT]`
- **Description**: Generates RFC 4122 v4 Universally Unique Identifiers (UUIDs) using high-entropy cryptographic seeds.
- **Usage Examples**:
  ```bash
  uuidgen
  uuidgen -n 5
  ```

### `unzip`
- **Syntax**: `unzip [-l] [-q] [-o] [-d DIR] ZIPFILE [FILE...]`
- **Description**: 100% pure-Rust PKZIP archive extractor and contents lister. Decompresses both stored (uncompressed) and DEFLATE compressed files, protecting against zip-slip directory traversals.
- **Usage Examples**:
  ```bash
  # Inspect archive without extraction
  unzip -l release.zip

  # Extract into target directory
  unzip release.zip -d /opt/app
  ```

### `lsof`
- **Syntax**: `lsof [-i [:[PORT]]] [-p PID] [FILE]`
- **Description**: Queries open files, network sockets, and listening ports across all processes, directly solving `EADDRINUSE` port conflict errors.
- **Usage Examples**:
  ```bash
  # Find what process is holding port 8080
  lsof -i :8080

  # List open files for process
  lsof -p 1240
  ```

### `fuser`
- **Syntax**: `fuser [-k] [-v] [FILE|PORT/tcp|PORT/udp]`
- **Description**: Identifies processes using files or network sockets. With `-k`, automatically terminates the offending process with `SIGKILL`.
- **Usage Examples**:
  ```bash
  # Identify PID using port 3000
  fuser 3000/tcp

  # Terminate process holding port 8080
  fuser -k 8080/tcp
  ```

### `dig`, `nslookup` & `host`
- **Syntax**: 
  - `dig [@SERVER] [-p PORT] DOMAIN [TYPE]`
  - `nslookup DOMAIN [SERVER]`
  - `host DOMAIN [SERVER]`
- **Description**: Pure-Rust DNS client querying standard A, AAAA, CNAME, TXT, and MX records against custom nameservers or default resolvers.
- **Usage Examples**:
  ```bash
  dig @1.1.1.1 google.com A
  nslookup internal.cluster.local 10.96.0.10
  host api.github.com
  ```

### `install` (GNU Mode / File Copier)
- **Syntax**: `install [-d] [-m MODE] [-v] SOURCE... DEST`
- **Description**: GNU-compatible file and directory installation tool used by standard Makefiles and build scripts (`install -d -m 755 /usr/local/bin`).
- **Usage Examples**:
  ```bash
  install -d -m 755 /usr/local/bin
  install -m 755 -v build/mydaemon /usr/local/bin/
  ```

### `patch`
- **Syntax**: `patch [-p NUM] [-R] [-i PATCHFILE] [ORIGFILE]`
- **Description**: Applies unified diff patches (`diff -u`) to source trees, supporting path segment stripping (`-p1`) and reverse patching (`-R`).
- **Usage Examples**:
  ```bash
  patch -p1 < bugfix.patch
  patch -i update.patch /var/www/index.html
  ```

### `json`
- **Syntax**: `json [-p] [-r] [--keys] [SELECTOR] [FILE]`
- **Description**: Lightweight streaming JSON parser, pretty-printer, and property query tool for cloud metadata and REST APIs.
- **Usage Examples**:
  ```bash
  # Pretty-print JSON
  cat payload.json | json -p

  # Extract nested field
  curl -s http://api/info | json -r .version

  # List top-level keys
  cat data.json | json --keys
  ```

### `ssl-check` / `cert`
- **Syntax**: `ssl-check [-p PORT] HOST`
- **Description**: Diagnostic utility for testing TLS endpoints, verifying X.509 validity dates, and diagnosing certificate expiration.
- **Usage Examples**:
  ```bash
  ssl-check google.com
  ssl-check -p 8443 internal.vault.service
  ```

### `lsattr` & `chattr`
- **Syntax**: 
  - `lsattr [-R] [FILE...]`
  - `chattr [+-=flags] [FILE...]`
- **Description**: Inspects and configures Linux ext4/btrfs/xfs inode attributes (`+i` immutable, `+a` append-only).
- **Usage Examples**:
  ```bash
  lsattr /etc/resolv.conf
  chattr +i /etc/resolv.conf
  ```

### `awk`
- **Syntax**: `awk [-F fs] [-v var=val] [-f progfile | 'program'] [file ...]`
- **Description**: Lightweight, pure-Rust pattern scanning and text processing language. Supports custom field separators (`-F:`), line and column numbers (`NR`, `NF`), record references (`$0`, `$1`..`$NF`), comparison patterns, regex matches (`/pattern/`), and `BEGIN` / `END` blocks.
- **Usage Examples**:
  ```bash
  # Print column 1 and column 3
  awk '{print $1, $3}' /etc/hosts

  # Parse /etc/passwd with colon delimiter
  awk -F: '{print $1, $7}' /etc/passwd

  # Skip header and sum column 2
  awk 'NR > 1 {sum += $2} END {print "Total:", sum}' data.csv

  # Match regex pattern
  awk '/ERROR/ {print $0}' /var/log/syslog
  ```

### `vi` & `ed` (Emergency Recovery Editors)
- **Syntax**: 
  - `vi [FILE]`
  - `ed [-p PROMPT] [-s] [FILE]`
- **Description**: Self-contained emergency text editors designed for rescue mode, broken system repair, and container debugging. `vi` provides full-screen modal editing (Normal mode, Insert mode, line navigation, `:w`, `:q`, `:wq`, undo `u`), automatically falling back to line mode when running non-interactively. `ed` provides the standard POSIX scriptable line editor.
- **Usage Examples**:
  ```bash
  # Interactive rescue editing
  vi /etc/fstab

  # Scripted file modification via ed
  printf "a\nnameserver 1.1.1.1\n.\nw\nq\n" | ed /etc/resolv.conf

  # Inspect all lines with line numbers
  printf ",n\nq\n" | ed /etc/hosts
  ```

### `proc-ledger` (Process Lifecycle & Relationship Ledger)
- **Syntax**: `proc-ledger [--active | --idle | --ghosts]`
- **Description**: Relational process ledger separating active CPU-consuming workloads from idle/safely-parked daemons and alerting to ghost/zombies. Solves process ambiguity by explicitly confirming dormant state and zero leaked CPU cycles.
- **Usage Examples**:
  ```bash
  # View complete dual-table ledger
  proc-ledger

  # Show only executing active workloads
  proc-ledger --active

  # Show only zombie (Z) and stuck D-state processes
  proc-ledger --ghosts
  ```

### `proc-kill` (Verified Process Termination)
- **Syntax**: `proc-kill [-signal] <PID>`
- **Description**: Enhanced process termination utility that sends the signal and immediately executes a post-termination verification probe. Confirms whether the process actually died, freed its resources, became a zombie, or hung in D-state. Also available via standard `kill -v <PID>`.
- **Usage Examples**:
  ```bash
  # Terminate and verify clean exit
  proc-kill 1420

  # Force kill with post-mortem diagnosis
  proc-kill -9 1420
  ```

### `pstree` (Visual Process Hierarchy Tree)
- **Syntax**: `pstree`
- **Description**: Visualizes running processes as an ASCII tree rooted at PID 1, displaying parent-child relationships, sub-workers, and category tags.
- **Usage Examples**:
  ```bash
  pstree
  ```

### `ghost-hunter` (Dead & Stuck Resource Detector)
- **Syntax**: `ghost-hunter`
- **Description**: Proactively scans the operating system for zombie processes (`Z`), uninterruptible disk-sleep processes (`D`), and unlinked open deleted files holding disk blocks.
- **Usage Examples**:
  ```bash
  ghost-hunter
  ```

### `dos2unix` & `unix2dos` (Cross-OS Line Break Cleaner)
- **Syntax**: 
  - `dos2unix [FILE...]`
  - `unix2dos [FILE...]`
- **Description**: Converts CRLF (`\r\n`) to LF (`\n`) and strips UTF-8 BOMs in-place or via stdin, eliminating the `\r: command not found` error across cross-platform repositories.
- **Usage Examples**:
  ```bash
  # Clean script in place
  dos2unix deploy.sh

  # Pipeline conversion
  cat windows.txt | dos2unix > unix.txt
  ```

### `sponge` (Atomic Pipeline Soak & Write)
- **Syntax**: `sponge [FILE]`
- **Description**: Buffers all standard input in memory before opening and writing to the target file atomically via temporary swap. Prevents the disastrous 0-byte file truncation bug when reading and writing to the same file (`cat file | grep -v bad | sponge file`).
- **Usage Examples**:
  ```bash
  # Safely filter a file in-place without wiping it
  grep -v "unwanted" config.json | sponge config.json
  ```

### `ts` (Real-Time Stream Timestamping)
- **Syntax**: `ts [FORMAT]`
- **Description**: Prepends precise timestamps to every line of standard input in real time. Default format is `[%H:%M:%S]`. Supports `%Y`, `%m`, `%d`, `%H`, `%M`, `%S`, and `%ms`.
- **Usage Examples**:
  ```bash
  # Timestamp compiler or build logs
  make build | ts "[%Y-%m-%d %H:%M:%S]"

  # Timestamp ping or network tests
  ping 1.1.1.1 | ts
  ```

---

## 15. Gap Analysis & Roadmap: What More We Need

For complete multi-OS comparative audit findings and package-level taxonomy, see [MULTI_OS_COMMANDS_AND_UTILITIES_COMPARATIVE_ANALYSIS.md](file:///Users/praveenkumar/rust%20os/docs/MULTI_OS_COMMANDS_AND_UTILITIES_COMPARATIVE_ANALYSIS.md).

| Priority | Utility | Functionality / Purpose | Status / Milestone |
| :--- | :--- | :--- | :--- |
| **Complete** | `awk` | Pure-Rust pattern scanning and column processing language | **Implemented in v2.3+** |
| **Complete** | `vi`, `ed` | Full-screen modal & POSIX scriptable recovery editor | **Implemented in v2.3+** |
| **Complete** | `gzip`, `gunzip`, `zcat` | RFC 1952 DEFLATE stream compression and decompression | **Implemented in v2.3+** |
| **Complete** | `unzip` | Pure-Rust PKZIP archive extraction and inspection (`-l`, `-d`) | **Implemented in v2.3+** |
| **Complete** | `envsubst` | Environment variable template substitution in containers | **Implemented in v2.3+** |
| **Complete** | `uuidgen` / `uuid` | RFC 4122 v4 Universally Unique Identifier generation | **Implemented in v2.3+** |
| **Complete** | `lsof`, `fuser` | Port conflict resolver and file descriptor inspector (`-k`, `-i`) | **Implemented in v2.3+** |
| **Complete** | `dig`, `nslookup`, `host` | Pure-Rust DNS client (A, AAAA, CNAME, TXT, MX) | **Implemented in v2.3+** |
| **Complete** | `install` (GNU) | Standard Makefile binary installation and mode configuration | **Implemented in v2.3+** |
| **Complete** | `patch` | POSIX unified diff patch applier (`-p NUM`, `-R`) | **Implemented in v2.3+** |
| **Complete** | `json` | Streaming JSON parser, query selector, and formatter | **Implemented in v2.3+** |
| **Complete** | `ssl-check` / `cert` | TLS certificate expiration and endpoint security probe | **Implemented in v2.3+** |
| **Complete** | `lsattr`, `chattr` | Inode attribute inspection and immutable control | **Implemented in v2.3+** |
| **Complete** | `dd` | Bit-level data duplication and block copying (`if=`, `of=`, `bs=`, `conv=fsync`) | **Implemented in v2.3+** |
| **Complete** | `time` | High-precision process timing (real, user, sys CPU time, RSS) | **Implemented in v2.3+** |
| **Complete** | `pidof` | Process ID lookup by executable name (`-s` single shot) | **Implemented in v2.3+** |
| **Complete** | `flock` | Kernel advisory file locks (`-s`, `-x`, `-n`) | **Implemented in v2.3+** |
| **Complete** | `nc` / `netcat` | TCP streaming, port readiness probing (`-z`), listener (`-l`) | **Implemented in v2.3+** |
| **Complete** | `route` | Kernel IP routing table inspection (net-tools format) | **Implemented in v2.3+** |
| **Complete** | `printf` | POSIX formatted string generator (`%s`, `%d`, `%x`) | **Implemented in v2.3+** |
| **Complete** | `rmdir` | Empty directory removal (`-p` parent hierarchy) | **Implemented in v2.3+** |
| **Complete** | `mknod`, `mkfifo` | Device node and named pipe creation (`libc::mknod`, `libc::mkfifo`) | **Implemented in v2.3+** |
| **Complete** | `cls`, `tasklist`, `where` | Windows developer ergonomic shims | **Implemented in v2.3+** |
| **High** | `bzip2`, `bunzip2` | Bzip2 block-sorting compression algorithm | Roadmap v2.4 |
| **High** | `xz`, `unxz` | LZMA2 / XZ compression for kernel images and packages | Roadmap v2.4 |
| **Medium** | `losetup` | Loop device setup and detachment (`/dev/loopX`) for mounting ISO/disk images | Roadmap v2.5 |
| **Medium** | `cpio` | Archive format essential for `initramfs` creation and extraction | Roadmap v2.5 |
| **Medium** | `top` / `htop` | Interactive terminal process monitor with CPU/RAM usage bars | Roadmap v2.5 |
| **Medium** | `fdisk` / `parted` | Partition table manipulation (MBR and GPT) | Roadmap v2.5 |
| **Low** | `cron` / `crontab` | Recurring background job scheduler daemon | Roadmap v2.6 |
| **Low** | `strace` | Dynamic system call tracer via `ptrace(2)` | Roadmap v2.6 |
| **Low** | `iptables` / `nftables` | Packet filtering and NAT rule configuration | Roadmap v2.6 |

---

## 16. Verification & Differential Parity Test Suite

To verify all utilities, run the continuous integration test harnesses:

```bash
# 1. Run all workspace unit tests (85 tests)
cargo test --workspace

# 2. Build the optimized release binary
cargo build --release --bin ferro-core

# 3. Run the Supervisor & Micro-Container Test Suite
python3 tools/test_supervisor_and_container.py

# 4. Run the Sandbox & Storage Differential Parity Suite (vs Ubuntu 24.04)
python3 tools/test_sandbox_and_storage_differential.py

# 5. List all registered applets (210 applets)
./target/release/ferro-core --list-applets
```
