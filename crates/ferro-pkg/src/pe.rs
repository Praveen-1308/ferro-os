//! Pure-Rust Windows Portable Executable (PE/COFF) Parser & Win32 API Stub Analyzer
//! Inspects PE32/PE32+ binaries, parses sections and imports, and evaluates native
//! Win32 entrypoint coverage on FerroOS.

use std::fs::File;
use std::io::{self, Read};
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PeArchitecture {
    I386,       // 32-bit x86
    Amd64,      // 64-bit x86_64
    Arm64,      // 64-bit ARM64
    Unknown(u16),
}

impl PeArchitecture {
    pub fn description(&self) -> &'static str {
        match self {
            PeArchitecture::I386 => "32-bit Intel x86 (PE32)",
            PeArchitecture::Amd64 => "64-bit AMD64 / x86_64 (PE32+)",
            PeArchitecture::Arm64 => "64-bit ARM64 / AArch64 (PE32+)",
            PeArchitecture::Unknown(_) => "Unknown Architecture",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PeSubsystem {
    Native,
    WindowsGui,
    WindowsCui, // Console
    PosixCui,
    WindowsCeGui,
    EfiApplication,
    Unknown(u16),
}

impl PeSubsystem {
    pub fn description(&self) -> &'static str {
        match self {
            PeSubsystem::Native => "Native Device Driver",
            PeSubsystem::WindowsGui => "Windows GUI (Graphical Interface)",
            PeSubsystem::WindowsCui => "Windows CUI (Console / Command Line)",
            PeSubsystem::PosixCui => "POSIX Console Subsystem",
            PeSubsystem::WindowsCeGui => "Windows CE GUI",
            PeSubsystem::EfiApplication => "EFI Firmware Application",
            PeSubsystem::Unknown(_) => "Unknown Subsystem",
        }
    }
}

#[derive(Debug, Clone)]
pub struct PeSection {
    pub name: String,
    pub virtual_size: u32,
    pub virtual_address: u32,
    pub raw_data_size: u32,
    pub raw_data_ptr: u32,
    pub characteristics: u32,
}

#[derive(Debug, Clone)]
pub struct PeImport {
    pub dll_name: String,
    pub functions: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct PeAnalysis {
    pub architecture: PeArchitecture,
    pub is_64bit: bool,
    pub subsystem: PeSubsystem,
    pub entry_point_rva: u32,
    pub image_base: u64,
    pub section_alignment: u32,
    pub file_alignment: u32,
    pub size_of_image: u32,
    pub sections: Vec<PeSection>,
    pub imports: Vec<PeImport>,
    pub native_stub_coverage_pct: f32,
    pub recommended_engine: String,
}

pub struct PeInspector {
    data: Vec<u8>,
}

impl PeInspector {
    pub fn open<P: AsRef<Path>>(path: P) -> io::Result<Self> {
        let mut file = File::open(path)?;
        let mut data = Vec::new();
        file.read_to_end(&mut data)?;
        Ok(Self { data })
    }

    pub fn from_bytes(data: Vec<u8>) -> Self {
        Self { data }
    }

    pub fn analyze(&self) -> io::Result<PeAnalysis> {
        if self.data.len() < 64 || &self.data[0..2] != b"MZ" {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Not a valid DOS/Windows MZ executable",
            ));
        }

        let pe_offset = u32::from_le_bytes([
            self.data[0x3C],
            self.data[0x3D],
            self.data[0x3E],
            self.data[0x3F],
        ]) as usize;

        if pe_offset + 24 > self.data.len() || &self.data[pe_offset..pe_offset + 4] != b"PE\0\0" {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Missing PE signature at e_lfanew offset",
            ));
        }

        // COFF Header (20 bytes following PE\0\0)
        let coff_off = pe_offset + 4;
        let machine_raw = u16::from_le_bytes([self.data[coff_off], self.data[coff_off + 1]]);
        let num_sections = u16::from_le_bytes([self.data[coff_off + 2], self.data[coff_off + 3]]) as usize;
        let opt_header_size = u16::from_le_bytes([self.data[coff_off + 16], self.data[coff_off + 17]]) as usize;

        let arch = match machine_raw {
            0x014C => PeArchitecture::I386,
            0x8664 => PeArchitecture::Amd64,
            0xAA64 => PeArchitecture::Arm64,
            other => PeArchitecture::Unknown(other),
        };

        // Optional Header
        let opt_off = coff_off + 20;
        if opt_off + opt_header_size > self.data.len() || opt_header_size < 28 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Invalid Optional Header in PE image",
            ));
        }

        let magic = u16::from_le_bytes([self.data[opt_off], self.data[opt_off + 1]]);
        let is_64bit = magic == 0x020B; // PE32+
        let entry_point_rva = u32::from_le_bytes([
            self.data[opt_off + 16],
            self.data[opt_off + 17],
            self.data[opt_off + 18],
            self.data[opt_off + 19],
        ]);

        let (image_base, section_align, file_align, size_of_image, subsystem_raw, import_dir_rva) = if is_64bit {
            let ib = u64::from_le_bytes([
                self.data[opt_off + 24], self.data[opt_off + 25], self.data[opt_off + 26], self.data[opt_off + 27],
                self.data[opt_off + 28], self.data[opt_off + 29], self.data[opt_off + 30], self.data[opt_off + 31],
            ]);
            let sa = u32::from_le_bytes([self.data[opt_off + 32], self.data[opt_off + 33], self.data[opt_off + 34], self.data[opt_off + 35]]);
            let fa = u32::from_le_bytes([self.data[opt_off + 36], self.data[opt_off + 37], self.data[opt_off + 38], self.data[opt_off + 39]]);
            let si = u32::from_le_bytes([self.data[opt_off + 56], self.data[opt_off + 57], self.data[opt_off + 58], self.data[opt_off + 59]]);
            let sub = u16::from_le_bytes([self.data[opt_off + 68], self.data[opt_off + 69]]);
            let imp_rva = if opt_header_size >= 120 {
                u32::from_le_bytes([self.data[opt_off + 120], self.data[opt_off + 121], self.data[opt_off + 122], self.data[opt_off + 123]])
            } else {
                0
            };
            (ib, sa, fa, si, sub, imp_rva)
        } else {
            let ib = u32::from_le_bytes([self.data[opt_off + 28], self.data[opt_off + 29], self.data[opt_off + 30], self.data[opt_off + 31]]) as u64;
            let sa = u32::from_le_bytes([self.data[opt_off + 32], self.data[opt_off + 33], self.data[opt_off + 34], self.data[opt_off + 35]]);
            let fa = u32::from_le_bytes([self.data[opt_off + 36], self.data[opt_off + 37], self.data[opt_off + 38], self.data[opt_off + 39]]);
            let si = u32::from_le_bytes([self.data[opt_off + 56], self.data[opt_off + 57], self.data[opt_off + 58], self.data[opt_off + 59]]);
            let sub = u16::from_le_bytes([self.data[opt_off + 68], self.data[opt_off + 69]]);
            let imp_rva = if opt_header_size >= 104 {
                u32::from_le_bytes([self.data[opt_off + 104], self.data[opt_off + 105], self.data[opt_off + 106], self.data[opt_off + 107]])
            } else {
                0
            };
            (ib, sa, fa, si, sub, imp_rva)
        };

        let subsystem = match subsystem_raw {
            1 => PeSubsystem::Native,
            2 => PeSubsystem::WindowsGui,
            3 => PeSubsystem::WindowsCui,
            7 => PeSubsystem::PosixCui,
            9 => PeSubsystem::WindowsCeGui,
            10 => PeSubsystem::EfiApplication,
            other => PeSubsystem::Unknown(other),
        };

        // Section Headers (each 40 bytes)
        let sec_table_off = opt_off + opt_header_size;
        let mut sections = Vec::new();
        for i in 0..num_sections {
            let s_off = sec_table_off + i * 40;
            if s_off + 40 > self.data.len() {
                break;
            }
            let name_bytes = &self.data[s_off..s_off + 8];
            let name = String::from_utf8_lossy(name_bytes).trim_matches(char::from(0)).to_string();
            let virt_size = u32::from_le_bytes([self.data[s_off + 8], self.data[s_off + 9], self.data[s_off + 10], self.data[s_off + 11]]);
            let virt_addr = u32::from_le_bytes([self.data[s_off + 12], self.data[s_off + 13], self.data[s_off + 14], self.data[s_off + 15]]);
            let raw_size = u32::from_le_bytes([self.data[s_off + 16], self.data[s_off + 17], self.data[s_off + 18], self.data[s_off + 19]]);
            let raw_ptr = u32::from_le_bytes([self.data[s_off + 20], self.data[s_off + 21], self.data[s_off + 22], self.data[s_off + 23]]);
            let charact = u32::from_le_bytes([self.data[s_off + 36], self.data[s_off + 37], self.data[s_off + 38], self.data[s_off + 39]]);

            sections.push(PeSection {
                name,
                virtual_size: virt_size,
                virtual_address: virt_addr,
                raw_data_size: raw_size,
                raw_data_ptr: raw_ptr,
                characteristics: charact,
            });
        }

        // Helper to convert RVA to file offset
        let rva_to_file = |rva: u32| -> Option<usize> {
            for sec in &sections {
                if rva >= sec.virtual_address && rva < sec.virtual_address + sec.virtual_size.max(sec.raw_data_size) {
                    let diff = rva - sec.virtual_address;
                    return Some((sec.raw_data_ptr + diff) as usize);
                }
            }
            None
        };

        // Parse Import Table
        let mut imports = Vec::new();
        if import_dir_rva > 0 {
            if let Some(mut imp_off) = rva_to_file(import_dir_rva) {
                while imp_off + 20 <= self.data.len() {
                    let name_rva = u32::from_le_bytes([self.data[imp_off + 12], self.data[imp_off + 13], self.data[imp_off + 14], self.data[imp_off + 15]]);
                    let first_thunk_rva = u32::from_le_bytes([self.data[imp_off + 16], self.data[imp_off + 17], self.data[imp_off + 18], self.data[imp_off + 19]]);
                    if name_rva == 0 && first_thunk_rva == 0 {
                        break;
                    }

                    let dll_name = if let Some(no) = rva_to_file(name_rva) {
                        let mut end = no;
                        while end < self.data.len() && self.data[end] != 0 {
                            end += 1;
                        }
                        String::from_utf8_lossy(&self.data[no..end]).to_string()
                    } else {
                        "UNKNOWN.DLL".to_string()
                    };

                    let mut func_names = Vec::new();
                    if let Some(mut thunk_off) = rva_to_file(first_thunk_rva) {
                        let step = if is_64bit { 8 } else { 4 };
                        while thunk_off + step <= self.data.len() {
                            let val = if is_64bit {
                                u64::from_le_bytes([
                                    self.data[thunk_off], self.data[thunk_off + 1], self.data[thunk_off + 2], self.data[thunk_off + 3],
                                    self.data[thunk_off + 4], self.data[thunk_off + 5], self.data[thunk_off + 6], self.data[thunk_off + 7],
                                ])
                            } else {
                                u32::from_le_bytes([self.data[thunk_off], self.data[thunk_off + 1], self.data[thunk_off + 2], self.data[thunk_off + 3]]) as u64
                            };
                            if val == 0 {
                                break;
                            }
                            let is_ordinal = if is_64bit { (val & 0x8000_0000_0000_0000) != 0 } else { (val & 0x8000_0000) != 0 };
                            if !is_ordinal {
                                if let Some(ibn_off) = rva_to_file(val as u32) {
                                    if ibn_off + 2 < self.data.len() {
                                        let mut fn_end = ibn_off + 2;
                                        while fn_end < self.data.len() && self.data[fn_end] != 0 {
                                            fn_end += 1;
                                        }
                                        let fname = String::from_utf8_lossy(&self.data[ibn_off + 2..fn_end]).to_string();
                                        if !fname.is_empty() {
                                            func_names.push(fname);
                                        }
                                    }
                                }
                            } else {
                                func_names.push(format!("Ordinal_{}", val & 0xFFFF));
                            }
                            thunk_off += step;
                        }
                    }

                    imports.push(PeImport {
                        dll_name,
                        functions: func_names,
                    });

                    imp_off += 20;
                }
            }
        }

        // Evaluate Stub Coverage against FerroOS Native Shims
        let supported_stubs = [
            "ExitProcess", "GetCommandLineA", "GetCommandLineW", "GetStdHandle",
            "WriteFile", "ReadFile", "VirtualAlloc", "VirtualFree", "GetModuleHandleA",
            "GetModuleHandleW", "GetProcAddress", "HeapCreate", "HeapAlloc", "HeapFree",
            "Sleep", "GetLastError", "SetLastError", "CloseHandle", "CreateFileA", "CreateFileW"
        ];

        let mut total_funcs = 0;
        let mut covered_funcs = 0;
        let mut has_gui_imports = false;

        for imp in &imports {
            let dll_lower = imp.dll_name.to_lowercase();
            if dll_lower.contains("user32") || dll_lower.contains("gdi32") || dll_lower.contains("d3d") || dll_lower.contains("opengl32") {
                has_gui_imports = true;
            }
            for func in &imp.functions {
                total_funcs += 1;
                if supported_stubs.iter().any(|&s| s == func) {
                    covered_funcs += 1;
                }
            }
        }

        let coverage_pct = if total_funcs > 0 {
            (covered_funcs as f32 / total_funcs as f32) * 100.0
        } else {
            100.0
        };

        let recommended_engine = match arch {
            PeArchitecture::I386 => {
                "Wine WoW64 Subsystem (Requires 32-bit Address Remapping)".to_string()
            }
            PeArchitecture::Amd64 => {
                if has_gui_imports || subsystem == PeSubsystem::WindowsGui {
                    "Box64 + Wine64 Compatibility Engine (Direct Vulkan/Wayland Pipeline)".to_string()
                } else if coverage_pct >= 90.0 {
                    "FerroOS Native PE Loader Shim (mimalloc + sched_ext)".to_string()
                } else {
                    "Box64 + Wine64 Compatibility Engine".to_string()
                }
            }
            PeArchitecture::Arm64 => {
                "Direct Native AArch64 Wine / OS Execution".to_string()
            }
            PeArchitecture::Unknown(_) => "Standard Wine Emulation".to_string(),
        };

        Ok(PeAnalysis {
            architecture: arch,
            is_64bit,
            subsystem,
            entry_point_rva,
            image_base,
            section_alignment: section_align,
            file_alignment: file_align,
            size_of_image,
            sections,
            imports,
            native_stub_coverage_pct: coverage_pct,
            recommended_engine,
        })
    }
}
