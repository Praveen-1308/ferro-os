ENTRY(_start)

SECTIONS {
    /* Conventional load address for 64-bit kernels: 1MB or higher-half */
    . = 1M;

    .boot : ALIGN(4K) {
        KEEP(*(.multiboot_header))
    }

    .text : ALIGN(4K) {
        *(.text .text.*)
    }

    .rodata : ALIGN(4K) {
        *(.rodata .rodata.*)
    }

    .data : ALIGN(4K) {
        *(.data .data.*)
    }

    .bss : ALIGN(4K) {
        *(.bss .bss.*)
    }

    /DISCARD/ : {
        *(.eh_frame)
        *(.note .note.*)
    }
}
