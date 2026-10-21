//! FerroOS FD Store: Crash-Only & Zero-Downtime Socket Handover via SCM_RIGHTS
//! Allows daemons and services to deposit listening sockets with PID 1.
//! If a service crashes or upgrades, PID 1 hands back the listening socket
//! so clients experience zero dropped connections and zero TCP resets.

#![allow(dead_code)]

use std::collections::HashMap;
use std::fs;
use std::io;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::thread;

pub const DEFAULT_SOCKET_PATH: &str = "/run/ferro/fdstore.sock";
pub const FALLBACK_SOCKET_PATH: &str = "/tmp/ferro_fdstore.sock";
pub const MAX_STORED_FDS: usize = 512;

#[cfg(target_os = "linux")]
fn check_peer_authorization(sock_fd: libc::c_int) -> bool {
    unsafe {
        let mut ucred: libc::ucred = std::mem::zeroed();
        let mut len = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
        if libc::getsockopt(
            sock_fd,
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            &mut ucred as *mut _ as *mut libc::c_void,
            &mut len,
        ) == 0 {
            return ucred.uid == 0;
        }
    }
    false
}

#[cfg(not(target_os = "linux"))]
fn check_peer_authorization(_sock_fd: libc::c_int) -> bool {
    true
}

pub unsafe fn send_fd(sock: libc::c_int, fd_to_send: libc::c_int, text: &str) -> io::Result<()> {
    let mut iov = libc::iovec {
        iov_base: text.as_ptr() as *mut libc::c_void,
        iov_len: text.len(),
    };

    let mut cmsg_buf = [0u8; 64];
    let mut msghdr: libc::msghdr = std::mem::zeroed();
    msghdr.msg_iov = &mut iov;
    msghdr.msg_iovlen = 1;

    if fd_to_send >= 0 {
        msghdr.msg_control = cmsg_buf.as_mut_ptr() as *mut libc::c_void;
        msghdr.msg_controllen = libc::CMSG_SPACE(std::mem::size_of::<libc::c_int>() as u32) as _;

        let cmsg = libc::CMSG_FIRSTHDR(&msghdr);
        if !cmsg.is_null() {
            (*cmsg).cmsg_level = libc::SOL_SOCKET;
            (*cmsg).cmsg_type = libc::SCM_RIGHTS;
            (*cmsg).cmsg_len = libc::CMSG_LEN(std::mem::size_of::<libc::c_int>() as u32) as _;
            let data_ptr = libc::CMSG_DATA(cmsg) as *mut libc::c_int;
            *data_ptr = fd_to_send;
        }
    }

    let ret = libc::sendmsg(sock, &msghdr, 0);
    if ret < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

pub unsafe fn recv_fd(
    sock: libc::c_int,
    text_buf: &mut [u8],
) -> io::Result<(usize, Option<libc::c_int>)> {
    let mut iov = libc::iovec {
        iov_base: text_buf.as_mut_ptr() as *mut libc::c_void,
        iov_len: text_buf.len(),
    };

    let mut cmsg_buf = [0u8; 64];
    let mut msghdr: libc::msghdr = std::mem::zeroed();
    msghdr.msg_iov = &mut iov;
    msghdr.msg_iovlen = 1;
    msghdr.msg_control = cmsg_buf.as_mut_ptr() as *mut libc::c_void;
    msghdr.msg_controllen = cmsg_buf.len() as _;

    let ret = libc::recvmsg(sock, &mut msghdr, 0);
    if ret < 0 {
        return Err(io::Error::last_os_error());
    }

    let mut received_fd = None;
    let mut cmsg = libc::CMSG_FIRSTHDR(&msghdr);
    while !cmsg.is_null() {
        if (*cmsg).cmsg_level == libc::SOL_SOCKET && (*cmsg).cmsg_type == libc::SCM_RIGHTS {
            let data_ptr = libc::CMSG_DATA(cmsg) as *const libc::c_int;
            received_fd = Some(*data_ptr);
            break;
        }
        cmsg = libc::CMSG_NXTHDR(&msghdr, cmsg);
    }

    Ok((ret as usize, received_fd))
}

pub struct FdStoreServer {
    store: Arc<Mutex<HashMap<String, libc::c_int>>>,
}

impl FdStoreServer {
    pub fn new() -> Self {
        Self {
            store: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub fn start(&self) -> io::Result<thread::JoinHandle<()>> {
        let sock_path =
            if Path::new("/run/ferro").exists() || fs::create_dir_all("/run/ferro").is_ok() {
                DEFAULT_SOCKET_PATH
            } else {
                FALLBACK_SOCKET_PATH
            };

        let _ = fs::remove_file(sock_path);
        let listener = UnixListener::bind(sock_path)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = fs::set_permissions(sock_path, fs::Permissions::from_mode(0o600));
        }
        println!("[ferro-init] FD Store listener active on {}", sock_path);

        let store_clone = Arc::clone(&self.store);
        let handle = thread::spawn(move || {
            for stream in listener.incoming() {
                if let Ok(stream) = stream {
                    let store = Arc::clone(&store_clone);
                    thread::spawn(move || {
                        handle_client(stream, store);
                    });
                }
            }
        });

        Ok(handle)
    }
}

fn handle_client(stream: UnixStream, store: Arc<Mutex<HashMap<String, libc::c_int>>>) {
    use std::os::unix::io::AsRawFd;
    let raw_sock = stream.as_raw_fd();
    let mut buf = [0u8; 512];

    unsafe {
        let (n, recvd_fd) = match recv_fd(raw_sock, &mut buf) {
            Ok(res) => res,
            Err(_) => return,
        };

        if n == 0 {
            if let Some(fd) = recvd_fd {
                libc::close(fd);
            }
            return;
        }

        // Access Control Verification: Only root (UID 0) allowed to interact with PID 1 FD Store
        if !check_peer_authorization(raw_sock) {
            let _ = send_fd(raw_sock, -1, "ERROR PERMISSION_DENIED: Root UID 0 required\n");
            if let Some(fd) = recvd_fd {
                libc::close(fd);
            }
            return;
        }

        let msg = String::from_utf8_lossy(&buf[..n]).trim().to_string();
        let parts: Vec<&str> = msg.split_whitespace().collect();
        if parts.is_empty() {
            if let Some(fd) = recvd_fd {
                libc::close(fd);
            }
            return;
        }

        match parts[0] {
            "STORE" => {
                if parts.len() >= 2 {
                    let name = parts[1].to_string();
                    if name.is_empty() || name.len() > 64 || !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.') {
                        let _ = send_fd(raw_sock, -1, "ERROR Invalid service name\n");
                        if let Some(fd) = recvd_fd {
                            libc::close(fd);
                        }
                        return;
                    }

                    if let Some(fd) = recvd_fd {
                        let mut map = store.lock().unwrap();
                        if map.len() >= MAX_STORED_FDS && !map.contains_key(&name) {
                            let _ = send_fd(raw_sock, -1, "ERROR FD Store Capacity Exceeded (max 1024)\n");
                            libc::close(fd);
                            return;
                        }

                        if let Some(old_fd) = map.insert(name.clone(), fd) {
                            libc::close(old_fd);
                        }
                        let resp = format!("STORED {}\n", name);
                        let _ = send_fd(raw_sock, -1, &resp);
                        println!(
                            "  [FD Store] Stored descriptor {} for service '{}'",
                            fd, name
                        );
                    } else {
                        let _ = send_fd(raw_sock, -1, "ERROR No FD passed in SCM_RIGHTS\n");
                    }
                } else {
                    let _ = send_fd(raw_sock, -1, "ERROR Missing service name\n");
                    if let Some(fd) = recvd_fd {
                        libc::close(fd);
                    }
                }
            }
            "GET" => {
                if let Some(fd) = recvd_fd {
                    libc::close(fd);
                }
                if parts.len() >= 2 {
                    let name = parts[1];
                    let map = store.lock().unwrap();
                    if let Some(&stored_fd) = map.get(name) {
                        let dup_fd = libc::dup(stored_fd);
                        let resp = format!("FOUND {}\n", name);
                        let _ = send_fd(raw_sock, dup_fd, &resp);
                        libc::close(dup_fd);
                        println!("  [FD Store] Handed over descriptor for service '{}'", name);
                    } else {
                        let resp = format!("NOT_FOUND {}\n", name);
                        let _ = send_fd(raw_sock, -1, &resp);
                    }
                }
            }
            "LIST" => {
                if let Some(fd) = recvd_fd {
                    libc::close(fd);
                }
                let map = store.lock().unwrap();
                let mut list = String::new();
                for (k, v) in map.iter() {
                    list.push_str(&format!("{}: {}\n", k, v));
                }
                if list.is_empty() {
                    list = "EMPTY\n".to_string();
                }
                let _ = send_fd(raw_sock, -1, &list);
            }
            "REMOVE" => {
                if let Some(fd) = recvd_fd {
                    libc::close(fd);
                }
                if parts.len() >= 2 {
                    let name = parts[1];
                    let mut map = store.lock().unwrap();
                    if let Some(fd) = map.remove(name) {
                        libc::close(fd);
                        let resp = format!("REMOVED {}\n", name);
                        let _ = send_fd(raw_sock, -1, &resp);
                    } else {
                        let resp = format!("NOT_FOUND {}\n", name);
                        let _ = send_fd(raw_sock, -1, &resp);
                    }
                }
            }
            _ => {
                if let Some(fd) = recvd_fd {
                    libc::close(fd);
                }
                let _ = send_fd(raw_sock, -1, "ERROR Unknown Command\n");
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::os::unix::io::AsRawFd;

    #[test]
    fn test_fdstore_handover() {
        let test_sock = "/tmp/test_fdstore_unit.sock";
        let _ = fs::remove_file(test_sock);

        let listener = UnixListener::bind(test_sock).unwrap();
        let store: Arc<Mutex<HashMap<String, libc::c_int>>> = Arc::new(Mutex::new(HashMap::new()));

        let store_clone = Arc::clone(&store);
        let _srv = thread::spawn(move || {
            if let Ok((stream, _)) = listener.accept() {
                handle_client(stream, Arc::clone(&store_clone));
            }
            if let Ok((stream, _)) = listener.accept() {
                handle_client(stream, Arc::clone(&store_clone));
            }
        });

        // Create a real listening TCP socket
        let tcp = TcpListener::bind("127.0.0.1:0").unwrap();
        let tcp_fd = tcp.as_raw_fd();

        // 1. Store FD
        let client1 = UnixStream::connect(test_sock).unwrap();
        unsafe {
            send_fd(client1.as_raw_fd(), tcp_fd, "STORE test_service\n").unwrap();
            let mut buf = [0u8; 128];
            let (n, _) = recv_fd(client1.as_raw_fd(), &mut buf).unwrap();
            let resp = String::from_utf8_lossy(&buf[..n]);
            assert!(resp.contains("STORED test_service"));
        }

        // 2. Retrieve FD
        let client2 = UnixStream::connect(test_sock).unwrap();
        unsafe {
            send_fd(client2.as_raw_fd(), -1, "GET test_service\n").unwrap();
            let mut buf = [0u8; 128];
            let (n, recvd_fd) = recv_fd(client2.as_raw_fd(), &mut buf).unwrap();
            let resp = String::from_utf8_lossy(&buf[..n]);
            assert!(resp.contains("FOUND test_service"));
            let fd = recvd_fd.expect("Should receive open socket FD");
            assert!(fd >= 0);
            libc::close(fd);
        }

        let _ = fs::remove_file(test_sock);
    }
}
