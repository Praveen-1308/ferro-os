//! Pure-Rust Microsoft Installer (.msi) & OLE Compound File (Structured Storage) Parser
//! Extracts Windows installation packages directly into rootless prefixes on FerroOS
//! without requiring a full Windows virtual machine or native msiexec.exe.

use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};

/// Magic bytes for Microsoft Compound Document File (OLE CFBF)
pub const OLE_MAGIC: [u8; 8] = [0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1];

/// Magic bytes for Microsoft Cabinet (.cab)
pub const CAB_MAGIC: [u8; 4] = [0x4D, 0x53, 0x43, 0x46]; // 'MSCF'

/// Magic bytes for DOS/Windows PE executable
pub const PE_DOS_MAGIC: [u8; 2] = [0x4D, 0x5A]; // 'MZ'

#[derive(Debug, Clone)]
pub struct MsiStream {
    pub name: String,
    pub stream_type: u8, // 1 = Storage, 2 = Stream, 5 = Root
    pub start_sector: u32,
    pub size: u64,
    pub data: Vec<u8>,
}

#[derive(Debug, Clone)]
pub struct MsiSummary {
    pub total_streams: usize,
    pub cabinet_streams: Vec<String>,
    pub executable_binaries: Vec<String>,
    pub target_app_name: Option<String>,
}

#[derive(Debug)]
pub struct ExtractionReport {
    pub extracted_files: Vec<PathBuf>,
    pub total_bytes_extracted: u64,
    pub main_executable: Option<PathBuf>,
    pub desktop_shortcut: Option<PathBuf>,
}

pub struct MsiExtractor {
    data: Vec<u8>,
    pub streams: Vec<MsiStream>,
}

impl MsiExtractor {
    pub fn open(path: &Path) -> io::Result<Self> {
        let mut file = File::open(path)?;
        let mut data = Vec::new();
        file.read_to_end(&mut data)?;

        let mut extractor = Self {
            data,
            streams: Vec::new(),
        };

        extractor.parse()?;
        Ok(extractor)
    }

    pub fn from_bytes(bytes: Vec<u8>) -> io::Result<Self> {
        let mut extractor = Self {
            data: bytes,
            streams: Vec::new(),
        };
        extractor.parse()?;
        Ok(extractor)
    }

    fn parse(&mut self) -> io::Result<()> {
        if self.data.len() < 512 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "MSI archive is too small to contain a valid OLE header",
            ));
        }

        // Verify OLE CFBF Header
        if self.data[0..8] != OLE_MAGIC {
            // Check if file is directly a Cabinet archive (.cab) or raw PE
            if self.data.len() >= 4 && self.data[0..4] == CAB_MAGIC {
                self.streams.push(MsiStream {
                    name: "EmbeddedData.cab".to_string(),
                    stream_type: 2,
                    start_sector: 0,
                    size: self.data.len() as u64,
                    data: self.data.clone(),
                });
                return Ok(());
            }

            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Invalid MSI signature (expected OLE CFBF magic D0CF11E0A1B11AE1)",
            ));
        }

        let sector_shift = u16::from_le_bytes([self.data[30], self.data[31]]) as usize;
        let sector_size = 1 << sector_shift;
        if sector_size < 512 || sector_size > 65536 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("Unsupported OLE sector size (2^{})", sector_shift),
            ));
        }

        let first_dir_sector = u32::from_le_bytes([
            self.data[48],
            self.data[49],
            self.data[50],
            self.data[51],
        ]);

        let num_fat_sectors = u32::from_le_bytes([
            self.data[44],
            self.data[45],
            self.data[46],
            self.data[47],
        ]) as usize;

        // Parse first 109 DIFAT entries located in header
        let mut fat_sector_locs = Vec::new();
        for i in 0..109.min(num_fat_sectors) {
            let offset = 76 + i * 4;
            let loc = u32::from_le_bytes([
                self.data[offset],
                self.data[offset + 1],
                self.data[offset + 2],
                self.data[offset + 3],
            ]);
            if loc < 0xFFFFFFFD {
                fat_sector_locs.push(loc);
            }
        }

        // Build FAT table
        let mut fat = Vec::new();
        for &sec in &fat_sector_locs {
            let offset = 512 + (sec as usize) * sector_size;
            if offset + sector_size <= self.data.len() {
                for chunk in self.data[offset..offset + sector_size].chunks_exact(4) {
                    fat.push(u32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]));
                }
            }
        }

        // Follow directory sector chain
        let mut dir_bytes = Vec::new();
        let mut cur_dir_sec = first_dir_sector;
        let mut visited_secs = std::collections::HashSet::new();

        while cur_dir_sec < 0xFFFFFFFD && !visited_secs.contains(&cur_dir_sec) {
            visited_secs.insert(cur_dir_sec);
            let offset = 512 + (cur_dir_sec as usize) * sector_size;
            if offset + sector_size <= self.data.len() {
                dir_bytes.extend_from_slice(&self.data[offset..offset + sector_size]);
            }
            if (cur_dir_sec as usize) < fat.len() {
                cur_dir_sec = fat[cur_dir_sec as usize];
            } else {
                break;
            }
        }

        // Each directory entry is 128 bytes
        for entry in dir_bytes.chunks_exact(128) {
            let name_len = u16::from_le_bytes([entry[64], entry[65]]) as usize;
            if name_len < 2 || name_len > 64 {
                continue;
            }

            // UTF-16LE name decode
            let name_u16: Vec<u16> = entry[0..name_len - 2]
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect();
            let raw_name = String::from_utf16_lossy(&name_u16);
            let clean_name = raw_name.trim_matches(char::from(0)).to_string();

            if clean_name.is_empty() {
                continue;
            }

            let stream_type = entry[66];
            let start_sec = u32::from_le_bytes([entry[116], entry[117], entry[118], entry[119]]);
            let size = u64::from_le_bytes([
                entry[120], entry[121], entry[122], entry[123], entry[124], entry[125], entry[126],
                entry[127],
            ]);

            // Reconstruct stream data if type is Stream (2)
            let mut stream_data = Vec::new();
            if stream_type == 2 && size > 0 && size < 200_000_000 {
                let mut cur_sec = start_sec;
                let mut rem = size as usize;
                let mut chain_visited = std::collections::HashSet::new();

                while cur_sec < 0xFFFFFFFD && rem > 0 && !chain_visited.contains(&cur_sec) {
                    chain_visited.insert(cur_sec);
                    let off = 512 + (cur_sec as usize) * sector_size;
                    if off < self.data.len() {
                        let to_read = (sector_size).min(rem).min(self.data.len() - off);
                        stream_data.extend_from_slice(&self.data[off..off + to_read]);
                        rem -= to_read;
                    }
                    if (cur_sec as usize) < fat.len() {
                        cur_sec = fat[cur_sec as usize];
                    } else {
                        break;
                    }
                }
            }

            self.streams.push(MsiStream {
                name: clean_name,
                stream_type,
                start_sector: start_sec,
                size,
                data: stream_data,
            });
        }

        Ok(())
    }

    pub fn inspect(&self) -> MsiSummary {
        let mut cabinets = Vec::new();
        let mut executables = Vec::new();
        let mut candidate_name = None;

        for s in &self.streams {
            if s.name.ends_with(".cab") || s.name.contains("Data1") || s.name.contains("#Data") {
                cabinets.push(s.name.clone());
            }

            // Check if stream itself is an executable
            if s.data.len() >= 2 && s.data[0..2] == PE_DOS_MAGIC {
                executables.push(s.name.clone());
                if candidate_name.is_none() {
                    candidate_name = Some(s.name.trim_end_matches(".exe").to_string());
                }
            }

            // Search embedded cabinet streams for PE headers
            if s.data.len() >= 4 && &s.data[0..4] == CAB_MAGIC {
                // Parse simple CAB or scan for embedded files
                let embedded_pes = scan_for_pe_signatures(&s.data);
                for (_offset, name) in embedded_pes {
                    executables.push(format!("{}!{}", s.name, name));
                    if candidate_name.is_none() {
                        candidate_name = Some(name.trim_end_matches(".exe").to_string());
                    }
                }
            }
        }

        MsiSummary {
            total_streams: self.streams.len(),
            cabinet_streams: cabinets,
            executable_binaries: executables,
            target_app_name: candidate_name,
        }
    }

    pub fn extract_all(&self, target_dir: &Path) -> io::Result<ExtractionReport> {
        fs::create_dir_all(target_dir)?;

        let mut extracted = Vec::new();
        let mut total_bytes = 0u64;
        let mut main_exe = None;

        for s in &self.streams {
            if s.stream_type != 2 || s.data.is_empty() {
                continue;
            }

            // Sanitize stream filename against path traversal
            let safe_name = sanitize_filename(&s.name);
            let out_file = target_dir.join(&safe_name);

            // Write stream
            let mut f = File::create(&out_file)?;
            f.write_all(&s.data)?;
            total_bytes += s.data.len() as u64;
            extracted.push(out_file.clone());

            // Check if stream is PE executable
            if s.data.len() >= 2 && s.data[0..2] == PE_DOS_MAGIC {
                #[cfg(target_os = "linux")]
                {
                    use std::os::unix::fs::PermissionsExt;
                    let _ = fs::set_permissions(&out_file, fs::Permissions::from_mode(0o755));
                }
                if main_exe.is_none() {
                    main_exe = Some(out_file.clone());
                }
            }

            // If stream is a Cabinet archive, scan and extract embedded PE binaries
            if s.data.len() >= 4 && &s.data[0..4] == CAB_MAGIC {
                let embedded = scan_for_pe_signatures(&s.data);
                for (offset, bin_name) in embedded {
                    let bin_path = target_dir.join(sanitize_filename(&bin_name));
                    if offset < s.data.len() {
                        let pe_data = &s.data[offset..];
                        if let Ok(mut bf) = File::create(&bin_path) {
                            let _ = bf.write_all(pe_data);
                            total_bytes += pe_data.len() as u64;
                            #[cfg(target_os = "linux")]
                            {
                                use std::os::unix::fs::PermissionsExt;
                                let _ = fs::set_permissions(
                                    &bin_path,
                                    fs::Permissions::from_mode(0o755),
                                );
                            }
                            if main_exe.is_none() {
                                main_exe = Some(bin_path.clone());
                            }
                            extracted.push(bin_path);
                        }
                    }
                }
            }
        }

        // Generate .desktop shortcut if executable found
        let mut shortcut_path = None;
        if let Some(ref exe) = main_exe {
            let app_name = exe
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("WindowsApp");
            shortcut_path = self
                .generate_desktop_shortcut(target_dir, app_name, exe)
                .ok();
        }

        Ok(ExtractionReport {
            extracted_files: extracted,
            total_bytes_extracted: total_bytes,
            main_executable: main_exe,
            desktop_shortcut: shortcut_path,
        })
    }

    pub fn generate_desktop_shortcut(
        &self,
        target_dir: &Path,
        app_name: &str,
        exec_path: &Path,
    ) -> io::Result<PathBuf> {
        let clean_name = app_name.replace(['_', '-'], " ");
        let shortcut_content = format!(
            "[Desktop Entry]\n\
             Type=Application\n\
             Version=1.0\n\
             Name={clean_name}\n\
             GenericName=Windows Application (FerroOS Native Bridge)\n\
             Comment=Launched via ferro-core wine-launcher & mimalloc interposition\n\
             Exec=ferro-core win-run --prefix \"{dir}\" --profile gaming \"{exe}\"\n\
             Icon=application-x-ms-dos-executable\n\
             Terminal=false\n\
             Categories=Game;Utility;Wine;\n\
             StartupNotify=true\n",
            clean_name = clean_name,
            dir = target_dir.display(),
            exe = exec_path.display()
        );

        let shortcut_file = target_dir.join(format!("{}.desktop", app_name.to_lowercase()));
        let mut f = File::create(&shortcut_file)?;
        f.write_all(shortcut_content.as_bytes())?;

        // If running with standard Linux user paths, copy to ~/.local/share/applications/
        if let Some(home) = dirs_home() {
            let apps_dir = home.join(".local/share/applications");
            let _ = fs::create_dir_all(&apps_dir);
            let dest = apps_dir.join(format!("{}.desktop", app_name.to_lowercase()));
            let _ = fs::copy(&shortcut_file, dest);
        }

        Ok(shortcut_file)
    }
}

fn sanitize_filename(name: &str) -> String {
    let clean = name.replace(['/', '\\', ':', '*', '?', '"', '<', '>', '|', '!'], "_");
    clean.trim_start_matches('.').to_string()
}

fn scan_for_pe_signatures(data: &[u8]) -> Vec<(usize, String)> {
    let mut results = Vec::new();
    if data.len() < 128 {
        return results;
    }

    for i in 0..(data.len() - 128) {
        if data[i] == b'M' && data[i + 1] == b'Z' {
            let pe_offset_loc = i + 0x3C;
            if pe_offset_loc + 4 <= data.len() {
                let pe_offset = u32::from_le_bytes([
                    data[pe_offset_loc],
                    data[pe_offset_loc + 1],
                    data[pe_offset_loc + 2],
                    data[pe_offset_loc + 3],
                ]) as usize;

                if pe_offset > 0 && pe_offset < 1024 && (i + pe_offset + 4) <= data.len() {
                    let pe_sig = &data[i + pe_offset..i + pe_offset + 4];
                    if pe_sig == b"PE\0\0" {
                        results.push((i, format!("embedded_bin_{:x}.exe", i)));
                    }
                }
            }
        }
    }
    results
}

fn dirs_home() -> Option<PathBuf> {
    std::env::var_os("HOME").map(PathBuf::from)
}
