; Topos-Theoretic Bootloader - Roulette Kernel
; This implements the geometric morphism F: BraidTopos → x86_64Topos
; via sheaf-theoretic pullbacks in the program category

BITS 16
ORG 0x7C00

start:
    ; Phase 1: Establish the braid category site
    cli

    ; Set up stack (memory topos initialization)
    xor ax, ax
    mov ss, ax
    mov sp, 0x7C00

    ; Phase 2: Set up segments (real-mode identity mapping)
    mov ax, 0x07C0
    mov ds, ax
    mov es, ax
    mov [boot_drive], dl   ; preserve BIOS boot drive number

    ; Initialize COM1 so we can write categorical traces to serial
    call serial_init
    mov si, serial_msg_boot
    call serial_write_string

    ; Phase 3: Load kernel from disk (sheaf pullback)
    call load_kernel
    mov si, serial_msg_loaded
    call serial_write_string

    ; Phase 4: Jump to kernel (geometric morphism application)
    ; Jump to 0x1000:0x0000 (linear 0x100000) - kernel entry point
    jmp 0x1000:0x0000

serial_init:
    ; Configure COM1: 38400 baud, 8N1, FIFO disabled
    mov dx, 0x3F8 + 1
    xor al, al
    out dx, al            ; disable interrupts

    mov dx, 0x3F8 + 3
    mov al, 0x80
    out dx, al            ; enable DLAB

    mov dx, 0x3F8        ; divisor low byte
    mov al, 0x03         ; 38400 baud divisor low
    out dx, al

    mov dx, 0x3F8 + 1    ; divisor high byte
    xor al, al
    out dx, al

    mov dx, 0x3F8 + 3
    mov al, 0x03         ; 8 bits, no parity, one stop
    out dx, al

    mov dx, 0x3F8 + 2
    xor al, al
    out dx, al            ; disable FIFO

    mov dx, 0x3F8 + 4
    mov al, 0x03         ; DTR + RTS
    out dx, al
    ret

serial_write_string:
    lodsb
    test al, al
    jz .done
.wait:
    mov dx, 0x3F8 + 5
    in al, dx
    test al, 0x20
    jz .wait
    mov dx, 0x3F8
    mov al, [si-1]
    out dx, al
    jmp serial_write_string
.done:
    ret

load_kernel:
    ; Load kernel at 0x100000 (1MB mark) - matches kernel link address
    mov ah, 0x02        ; BIOS read sectors
    mov al, 64          ; Number of sectors to read (should be enough)
    mov ch, 0           ; Cylinder
    mov cl, 2           ; Sector (start after bootloader)
    mov dh, 0           ; Head
    mov dl, [boot_drive]

    ; Set ES:BX to 0x1000:0 to represent linear 0x100000
    mov bx, 0x1000
    mov es, bx
    xor bx, bx

    int 0x13
    jc load_error
    ret

load_error:
    ; Infinite loop on error - represents terminal object
    hlt
    jmp load_error

serial_msg_boot db "[boot] stage0", 0x0D, 0x0A, 0
serial_msg_loaded db "[boot] kernel loaded", 0x0D, 0x0A, 0
boot_drive db 0

; Pad to 510 bytes
times 510 - ($ - $$) db 0

; Boot signature
dw 0xAA55