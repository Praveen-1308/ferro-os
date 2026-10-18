//! ferro-pkg (rpk): Rust Package Keeper for FerroOS.
//! Fast, memory-safe package manager handling package installation,
//! removal, dependency tracking, and package creation.

use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use flate2::Compression;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use tar::{Archive, Builder};

const DB_PATH: &str = "/var/lib/rpk/db.json";

#[derive(Serialize, Deserialize, Debug, Clone)]
struct PackageMetadata {
    name: String,
    version: String,
    description: String,
    #[serde(default)]
    dependencies: Vec<String>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct InstalledPackage {
    metadata: PackageMetadata,
    installed_files: Vec<String>,
    installed_at: String,
}

#[derive(Serialize, Deserialize, Debug, Default)]
struct PackageDatabase {
    packages: HashMap<String, InstalledPackage>,
}

impl PackageDatabase {
    fn load() -> Self {
        if Path::new(DB_PATH).exists() {
            if let Ok(content) = fs::read_to_string(DB_PATH) {
                if let Ok(db) = serde_json::from_str(&content) {
                    return db;
                }
            }
        }
        PackageDatabase::default()
    }

    fn save(&self) -> io::Result<()> {
        if let Some(parent) = Path::new(DB_PATH).parent() {
            fs::create_dir_all(parent)?;
        }
        let data = serde_json::to_string_pretty(self)?;
        fs::write(DB_PATH, data)
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        print_usage();
        return ExitCode::SUCCESS;
    }

    match args[1].as_str() {
        "list" => cmd_list(),
        "info" => {
            if args.len() < 3 {
                eprintln!("rpk info: missing package name");
                return ExitCode::FAILURE;
            }
            cmd_info(&args[2])
        }
        "install" => {
            if args.len() < 3 {
                eprintln!("rpk install: missing package archive (.rpk or .tar.gz)");
                return ExitCode::FAILURE;
            }
            cmd_install(&args[2])
        }
        "remove" => {
            if args.len() < 3 {
                eprintln!("rpk remove: missing package name");
                return ExitCode::FAILURE;
            }
            cmd_remove(&args[2])
        }
        "build" => {
            if args.len() < 4 {
                eprintln!("rpk build: usage: rpk build <source_dir> <output.rpk>");
                return ExitCode::FAILURE;
            }
            cmd_build(&args[2], &args[3])
        }
        "help" | "--help" => {
            print_usage();
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("rpk: unknown command '{}'", args[1]);
            print_usage();
            ExitCode::FAILURE
        }
    }
}

fn print_usage() {
    println!("rpk - Rust Package Keeper for FerroOS v0.1.0");
    println!("Usage: rpk <command> [options]");
    println!("\nCommands:");
    println!("  list                  List all installed packages");
    println!("  info <package>        Show detailed package information");
    println!("  install <package.rpk> Install a package (.rpk or .tar.gz)");
    println!("  remove <package>      Uninstall a package and remove files");
    println!("  build <dir> <out.rpk> Build a new .rpk package from directory");
}

fn cmd_list() -> ExitCode {
    let db = PackageDatabase::load();
    if db.packages.is_empty() {
        println!("[rpk] No packages currently installed.");
        return ExitCode::SUCCESS;
    }

    println!("{:<20} {:<12} {}", "PACKAGE", "VERSION", "DESCRIPTION");
    println!("{:-<20} {:-<12} {:-<40}", "", "", "");
    for (name, pkg) in &db.packages {
        println!(
            "{:<20} {:<12} {}",
            name, pkg.metadata.version, pkg.metadata.description
        );
    }
    println!("\nTotal installed: {} packages", db.packages.len());
    ExitCode::SUCCESS
}

fn cmd_info(pkg_name: &str) -> ExitCode {
    let db = PackageDatabase::load();
    if let Some(pkg) = db.packages.get(pkg_name) {
        println!("Package:      {}", pkg.metadata.name);
        println!("Version:      {}", pkg.metadata.version);
        println!("Description:  {}", pkg.metadata.description);
        println!("Installed At: {}", pkg.installed_at);
        println!("Files:        {} files installed", pkg.installed_files.len());
        println!("\nFile list (first 10):");
        for f in pkg.installed_files.iter().take(10) {
            println!("  /{}", f);
        }
        if pkg.installed_files.len() > 10 {
            println!("  ... and {} more files", pkg.installed_files.len() - 10);
        }
        ExitCode::SUCCESS
    } else {
        eprintln!("rpk: package '{}' is not installed", pkg_name);
        ExitCode::FAILURE
    }
}

fn cmd_install(archive_path: &str) -> ExitCode {
    println!("[rpk] Opening package '{}'...", archive_path);
    let file = match File::open(archive_path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("rpk: cannot open file '{}': {}", archive_path, e);
            return ExitCode::FAILURE;
        }
    };

    let gz = GzDecoder::new(file);
    let mut archive = Archive::new(gz);

    let mut metadata: Option<PackageMetadata> = None;
    let mut installed_files: Vec<String> = Vec::new();

    let target_root = Path::new("/");

    let entries = match archive.entries() {
        Ok(e) => e,
        Err(e) => {
            eprintln!("rpk: corrupt tar archive: {}", e);
            return ExitCode::FAILURE;
        }
    };

    for entry_res in entries {
        let mut entry = match entry_res {
            Ok(e) => e,
            Err(e) => {
                eprintln!("rpk: error reading archive entry: {}", e);
                return ExitCode::FAILURE;
            }
        };

        let path = match entry.path() {
            Ok(p) => p.to_path_buf(),
            Err(_) => continue,
        };

        let path_str = path.to_string_lossy().to_string();

        if path_str == "package.json" {
            let mut content = String::new();
            let _ = entry.read_to_string(&mut content);
            if let Ok(meta) = serde_json::from_str::<PackageMetadata>(&content) {
                metadata = Some(meta);
            }
            continue;
        }

        // Unpack file or directory
        let dest = target_root.join(&path);
        if let Some(parent) = dest.parent() {
            let _ = fs::create_dir_all(parent);
        }

        if let Err(e) = entry.unpack(&dest) {
            eprintln!("rpk: warning: error unpacking '{}': {}", dest.display(), e);
        } else {
            installed_files.push(path_str);
        }
    }

    let meta = metadata.unwrap_or_else(|| {
        let fallback_name = Path::new(archive_path)
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        PackageMetadata {
            name: fallback_name,
            version: "1.0.0".to_string(),
            description: "Installed via rpk".to_string(),
            dependencies: Vec::new(),
        }
    });

    let mut db = PackageDatabase::load();
    let pkg_name = meta.name.clone();
    let version = meta.version.clone();

    db.packages.insert(
        pkg_name.clone(),
        InstalledPackage {
            metadata: meta,
            installed_files,
            installed_at: "system startup".to_string(),
        },
    );

    if let Err(e) = db.save() {
        eprintln!("rpk: warning: failed to update database: {}", e);
    }

    println!(
        "[rpk]  Successfully installed {} v{}!",
        pkg_name, version
    );
    ExitCode::SUCCESS
}

fn cmd_remove(pkg_name: &str) -> ExitCode {
    let mut db = PackageDatabase::load();
    if let Some(pkg) = db.packages.remove(pkg_name) {
        println!("[rpk] Removing package '{}'...", pkg_name);
        for file in pkg.installed_files {
            let full_path = PathBuf::from("/").join(file);
            if full_path.is_file() {
                let _ = fs::remove_file(full_path);
            }
        }
        let _ = db.save();
        println!("[rpk]  Successfully removed {}!", pkg_name);
        ExitCode::SUCCESS
    } else {
        eprintln!("rpk: package '{}' not found", pkg_name);
        ExitCode::FAILURE
    }
}

fn cmd_build(source_dir: &str, output_path: &str) -> ExitCode {
    println!("[rpk] Building package from '{}' -> '{}'...", source_dir, output_path);
    let src = Path::new(source_dir);
    if !src.is_dir() {
        eprintln!("rpk: source directory '{}' does not exist", source_dir);
        return ExitCode::FAILURE;
    }

    let out_file = match File::create(output_path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("rpk: cannot create output file '{}': {}", output_path, e);
            return ExitCode::FAILURE;
        }
    };

    let gz = GzEncoder::new(out_file, Compression::default());
    let mut tar = Builder::new(gz);

    if let Err(e) = tar.append_dir_all(".", src) {
        eprintln!("rpk: error archiving directory: {}", e);
        return ExitCode::FAILURE;
    }

    if let Err(e) = tar.finish() {
        eprintln!("rpk: error finalizing package: {}", e);
        return ExitCode::FAILURE;
    }

    println!("[rpk]  Package built successfully: {}", output_path);
    ExitCode::SUCCESS
}
