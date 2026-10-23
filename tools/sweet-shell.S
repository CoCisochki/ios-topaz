#define SYS_exit 1
#define SYS_fork 2
#define SYS_read 3
#define SYS_write 4
#define SYS_open 5
#define SYS_close 6
#define SYS_wait4 7
#define SYS_getpid 20
#define SYS_kill 37
#define SYS_dup2 90
#define SYS_socket 97
#define SYS_bind 104
#define SYS_setsockopt 105
#define SYS_listen 106
#define SYS_accept 30
#define SYS_execve 59
#define SYS_reboot 55
#define SYS_getdirentries64 344

#define AF_INET 2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define SOL_SOCKET 0xffff
#define SO_REUSEADDR 4
#define O_RDONLY 0

	.text
	.globl	_start
	.p2align 2

_start:
	mov	x9, sp
	and	x9, x9, #~15
	mov	sp, x9

	mov	x0, #AF_INET
	mov	x1, #SOCK_STREAM
	mov	x2, #IPPROTO_TCP
	mov	x16, #SYS_socket
	svc	#0x80
	b.cs	fatal_exit
	mov	x19, x0

	mov	w0, #1
	sub	sp, sp, #16
	str	w0, [sp]
	mov	x0, x19
	mov	x1, #SOL_SOCKET
	mov	x2, #SO_REUSEADDR
	mov	x3, sp
	mov	x4, #4
	mov	x16, #SYS_setsockopt
	svc	#0x80
	add	sp, sp, #16

	sub	sp, sp, #16
	mov	w0, #0x0210
	movk	w0, #0x3905, lsl #16
	str	w0, [sp]
	str	wzr, [sp, #4]
	str	xzr, [sp, #8]
	mov	x0, x19
	mov	x1, sp
	mov	x2, #16
	mov	x16, #SYS_bind
	svc	#0x80
	add	sp, sp, #16
	b.cs	fatal_exit

	mov	x0, x19
	mov	x1, #5
	mov	x16, #SYS_listen
	svc	#0x80
	b.cs	fatal_exit

accept_loop:
	mov	x0, x19
	mov	x1, #0
	mov	x2, #0
	mov	x16, #SYS_accept
	svc	#0x80
	b.cs	accept_loop
	mov	x20, x0

	adr	x1, str_banner
	adr	x2, str_banner_end
	sub	x2, x2, x1
	bl	sock_write

prompt_loop:
	adr	x1, str_prompt
	adr	x2, str_prompt_end
	sub	x2, x2, x1
	bl	sock_write

	sub	sp, sp, #512
	mov	x0, x20
	mov	x1, sp
	mov	x2, #511
	mov	x16, #SYS_read
	svc	#0x80
	b.cs	conn_closed
	cmp	x0, #0
	b.le	conn_closed

	mov	x21, x0
	mov	x22, sp
	add	x23, x22, x21
	strb	wzr, [x23]

strip_loop:
	cmp	x21, #0
	b.eq	parse_cmd
	sub	x23, x23, #1
	ldrb	w24, [x23]
	cmp	w24, #'\r'
	b.eq	strip_char
	cmp	w24, #'\n'
	b.eq	strip_char
	b	parse_cmd

strip_char:
	strb	wzr, [x23]
	sub	x21, x21, #1
	b	strip_loop

parse_cmd:
	cmp	x21, #0
	b.eq	free_and_prompt

	ldrb	w0, [x22]
	cmp	w0, #'h'
	b.ne	check_ls
	adr	x1, str_help_cmd
	bl	str_prefix
	cbz	x0, do_help

check_ls:
	cmp	w0, #'l'
	b.ne	check_cat
	adr	x1, str_ls_cmd
	bl	str_prefix
	cbz	x0, do_ls

check_cat:
	cmp	w0, #'c'
	b.ne	check_ps
	adr	x1, str_cat_cmd
	bl	str_prefix
	cbz	x0, do_cat

check_ps:
	cmp	w0, #'p'
	b.ne	check_dmesg
	adr	x1, str_ps_cmd
	bl	str_prefix
	cbz	x0, do_ps

check_dmesg:
	cmp	w0, #'d'
	b.ne	check_uname
	adr	x1, str_dmesg_cmd
	bl	str_prefix
	cbz	x0, do_dmesg

check_uname:
	cmp	w0, #'u'
	b.ne	check_reboot
	adr	x1, str_uname_cmd
	bl	str_prefix
	cbz	x0, do_uname

check_reboot:
	cmp	w0, #'r'
	b.ne	check_exit
	adr	x1, str_reboot_cmd
	bl	str_prefix
	cbz	x0, do_reboot

check_exit:
	cmp	w0, #'e'
	b.ne	check_quit
	adr	x1, str_exit_cmd
	bl	str_prefix
	cbz	x0, do_exit

check_quit:
	cmp	w0, #'q'
	b.ne	check_exec
	adr	x1, str_quit_cmd
	bl	str_prefix
	cbz	x0, do_exit

check_exec:
	adr	x1, str_exec_cmd
	bl	str_prefix
	cbz	x0, do_exec

	adr	x1, str_unknown
	adr	x2, str_unknown_end
	sub	x2, x2, x1
	bl	sock_write
	b	free_and_prompt

do_help:
	adr	x1, str_help_text
	adr	x2, str_help_text_end
	sub	x2, x2, x1
	bl	sock_write
	b	free_and_prompt

do_uname:
	adr	x1, str_uname_text
	adr	x2, str_uname_text_end
	sub	x2, x2, x1
	bl	sock_write
	b	free_and_prompt

do_reboot:
	adr	x1, str_reboot_text
	adr	x2, str_reboot_text_end
	sub	x2, x2, x1
	bl	sock_write
	mov	x0, #1
	mov	x1, #9
	mov	x16, #SYS_kill
	svc	#0x80
	b	conn_closed

do_exit:
	adr	x1, str_bye
	adr	x2, str_bye_end
	sub	x2, x2, x1
	bl	sock_write
	b	conn_closed

do_cat:
	add	x24, x22, #3
skip_cat_sp:
	ldrb	w25, [x24]
	cmp	w25, #' '
	b.ne	cat_path_ready
	add	x24, x24, #1
	b	skip_cat_sp

cat_path_ready:
	ldrb	w25, [x24]
	cbz	w25, cat_no_arg
	mov	x0, x24
	mov	x1, #O_RDONLY
	mov	x2, #0
	mov	x16, #SYS_open
	svc	#0x80
	b.cs	cat_open_err
	mov	x25, x0

cat_read_loop:
	sub	sp, sp, #1024
	mov	x0, x25
	mov	x1, sp
	mov	x2, #1024
	mov	x16, #SYS_read
	svc	#0x80
	b.cs	cat_read_done
	cmp	x0, #0
	b.le	cat_read_done
	mov	x2, x0
	mov	x1, sp
	bl	sock_write
	add	sp, sp, #1024
	b	cat_read_loop

cat_read_done:
	add	sp, sp, #1024
	mov	x0, x25
	mov	x16, #SYS_close
	svc	#0x80
	b	free_and_prompt

cat_no_arg:
	adr	x1, str_cat_usage
	adr	x2, str_cat_usage_end
	sub	x2, x2, x1
	bl	sock_write
	b	free_and_prompt

cat_open_err:
	adr	x1, str_err_open
	adr	x2, str_err_open_end
	sub	x2, x2, x1
	bl	sock_write
	b	free_and_prompt

do_dmesg:
	adr	x0, str_klog_path
	mov	x1, #O_RDONLY
	mov	x2, #0
	mov	x16, #SYS_open
	svc	#0x80
	b.cs	dmesg_fallback
	mov	x25, x0

dmesg_read_loop:
	sub	sp, sp, #1024
	mov	x0, x25
	mov	x1, sp
	mov	x2, #1024
	mov	x16, #SYS_read
	svc	#0x80
	b.cs	dmesg_done
	cmp	x0, #0
	b.le	dmesg_done
	mov	x2, x0
	mov	x1, sp
	bl	sock_write
	add	sp, sp, #1024
	b	dmesg_read_loop

dmesg_done:
	add	sp, sp, #1024
	mov	x0, x25
	mov	x16, #SYS_close
	svc	#0x80
	b	free_and_prompt

dmesg_fallback:
	adr	x1, str_klog_err
	adr	x2, str_klog_err_end
	sub	x2, x2, x1
	bl	sock_write
	b	free_and_prompt

do_ps:
	adr	x1, str_ps_header
	adr	x2, str_ps_header_end
	sub	x2, x2, x1
	bl	sock_write

	mov	x24, #1
ps_loop:
	mov	x0, x24
	mov	x1, #0
	mov	x16, #SYS_kill
	svc	#0x80
	b.cc	ps_found
	cmp	x0, #1
	b.eq	ps_found
	b	ps_next

ps_found:
	mov	x0, x24
	bl	print_pid_line

ps_next:
	add	x24, x24, #1
	cmp	x24, #500
	b.le	ps_loop
	b	free_and_prompt

do_ls:
	add	x24, x22, #2
skip_ls_sp:
	ldrb	w25, [x24]
	cmp	w25, #' '
	b.ne	ls_path_ready
	add	x24, x24, #1
	b	skip_ls_sp

ls_path_ready:
	ldrb	w25, [x24]
	cbnz	w25, ls_open
	adr	x24, str_dot

ls_open:
	mov	x0, x24
	mov	x1, #O_RDONLY
	mov	x2, #0
	mov	x16, #SYS_open
	svc	#0x80
	b.cs	ls_open_err
	mov	x25, x0

ls_read_block:
	sub	sp, sp, #2048
	mov	x0, x25
	mov	x1, sp
	mov	x2, #2040
	sub	sp, sp, #16
	mov	x3, sp
	mov	x16, #SYS_getdirentries64
	svc	#0x80
	add	sp, sp, #16
	b.cs	ls_read_done
	cmp	x0, #0
	b.le	ls_read_done

	mov	x26, x0
	mov	x27, sp
ls_entry_loop:
	cmp	x26, #21
	b.lt	ls_read_done

	ldrh	w28, [x27, #16]
	cbz	w28, ls_read_done
	ldrh	w29, [x27, #18]
	cbz	w29, ls_next_entry

	add	x1, x27, #21
	mov	x2, x29
	bl	sock_write
	adr	x1, str_newline
	mov	x2, #1
	bl	sock_write

ls_next_entry:
	add	x27, x27, x28
	sub	x26, x26, x28
	b	ls_entry_loop

ls_read_done:
	add	sp, sp, #2048
	mov	x0, x25
	mov	x16, #SYS_close
	svc	#0x80
	b	free_and_prompt

ls_open_err:
	adr	x1, str_err_open
	adr	x2, str_err_open_end
	sub	x2, x2, x1
	bl	sock_write
	b	free_and_prompt

do_exec:
	add	x24, x22, #4
skip_exec_sp:
	ldrb	w25, [x24]
	cmp	w25, #' '
	b.ne	exec_path_ready
	add	x24, x24, #1
	b	skip_exec_sp

exec_path_ready:
	ldrb	w25, [x24]
	cbz	w25, exec_no_arg

	mov	x16, #SYS_fork
	svc	#0x80
	b.cs	exec_fork_err
	cbnz	x1, exec_child

	mov	x25, x0
	sub	sp, sp, #16
	mov	x0, x25
	mov	x1, sp
	mov	x2, #0
	mov	x3, #0
	mov	x16, #SYS_wait4
	svc	#0x80
	add	sp, sp, #16
	b	free_and_prompt

exec_child:
	mov	x0, x20
	mov	x1, #0
	mov	x16, #SYS_dup2
	svc	#0x80
	mov	x0, x20
	mov	x1, #1
	mov	x16, #SYS_dup2
	svc	#0x80
	mov	x0, x20
	mov	x1, #2
	mov	x16, #SYS_dup2
	svc	#0x80

	sub	sp, sp, #32
	str	x24, [sp]
	str	xzr, [sp, #8]
	mov	x0, x24
	mov	x1, sp
	mov	x2, #0
	mov	x16, #SYS_execve
	svc	#0x80
	mov	x0, #1
	mov	x16, #SYS_exit
	svc	#0x80

exec_fork_err:
	adr	x1, str_exec_fork_err
	adr	x2, str_exec_fork_err_end
	sub	x2, x2, x1
	bl	sock_write
	b	free_and_prompt

exec_no_arg:
	adr	x1, str_exec_usage
	adr	x2, str_exec_usage_end
	sub	x2, x2, x1
	bl	sock_write
	b	free_and_prompt

free_and_prompt:
	add	sp, sp, #512
	b	prompt_loop

conn_closed:
	add	sp, sp, #512
	mov	x0, x20
	mov	x16, #SYS_close
	svc	#0x80
	b	accept_loop

fatal_exit:
	mov	x0, #1
	mov	x16, #SYS_exit
	svc	#0x80

sock_write:
	str	lr, [sp, #-16]!
	mov	x0, x20
	mov	x16, #SYS_write
	svc	#0x80
	ldr	lr, [sp], #16
	ret

str_prefix:
	ldrb	w2, [x1]
	cbz	w2, str_pfx_match
	ldrb	w3, [x22]
	cbz	w3, str_pfx_nomatch
	cmp	w2, w3
	b.ne	str_pfx_nomatch
	add	x1, x1, #1
	add	x22, x22, #1
	b	str_prefix
str_pfx_match:
	mov	x0, #0
	ret
str_pfx_nomatch:
	mov	x0, #1
	ret

print_pid_line:
	str	lr, [sp, #-32]!
	str	x24, [sp, #8]
	sub	sp, sp, #32

	adr	x1, str_pid_prefix
	mov	x2, #5
	bl	sock_write

	mov	x1, x24
	add	x2, sp, #24
	strb	wzr, [x2]
	mov	x3, #10
pid_conv_loop:
	udiv	x4, x1, x3
	msub	x5, x4, x3, x1
	add	w5, w5, #'0'
	sub	x2, x2, #1
	strb	w5, [x2]
	mov	x1, x4
	cbnz	x1, pid_conv_loop

	add	x3, sp, #24
	sub	x2, x3, x2
	add	x1, sp, #24
	sub	x1, x1, x2
	bl	sock_write

	adr	x1, str_newline
	mov	x2, #1
	bl	sock_write

	add	sp, sp, #32
	ldr	x24, [sp, #8]
	ldr	lr, [sp], #32
	ret

	.text
str_banner:
	.ascii	"\r\n==========================================\r\n"
	.ascii	" Topaz (Redmi Note 12 4G) iOS 16.7 Shell \r\n"
	.ascii	" Listening on 0.0.0.0:1337                \r\n"
	.ascii	"==========================================\r\n"
	.ascii	"Type 'help' for available commands.\r\n"
str_banner_end:

str_prompt:
	.ascii	"topaz# "
str_prompt_end:

str_help_text:
	.ascii	"Available commands:\r\n"
	.ascii	"  help          Show this menu\r\n"
	.ascii	"  uname         Show kernel/device info\r\n"
	.ascii	"  ls <dir>      List directory contents\r\n"
	.ascii	"  cat <file>    Display file contents\r\n"
	.ascii	"  ps            List active processes (PIDs)\r\n"
	.ascii	"  dmesg         Show /dev/klog kernel log\r\n"
	.ascii	"  exec <bin>    Execute binary with fork/execve\r\n"
	.ascii	"  reboot        Reboot the device\r\n"
	.ascii	"  exit / quit   Disconnect\r\n"
str_help_text_end:

str_uname_text:
	.ascii	"Darwin topaz-d22ap 22.6.0 XNU (sweet-development-arm64) SM6225\r\n"
str_uname_text_end:

str_bye:
	.ascii	"Closing connection. Goodbye!\r\n"
str_bye_end:

str_reboot_text:
	.ascii	"Rebooting device now...\r\n"
str_reboot_text_end:

str_unknown:
	.ascii	"Unknown command. Type 'help' for a list.\r\n"
str_unknown_end:

str_cat_usage:
	.ascii	"Usage: cat <file_path>\r\n"
str_cat_usage_end:

str_exec_usage:
	.ascii	"Usage: exec <binary_path>\r\n"
str_exec_usage_end:

str_exec_fork_err:
	.ascii	"Error: fork failed\r\n"
str_exec_fork_err_end:

str_err_open:
	.ascii	"Error: could not open target\r\n"
str_err_open_end:

str_klog_err:
	.ascii	"Error: /dev/klog not available\r\n"
str_klog_err_end:

str_ps_header:
	.ascii	"Active Process IDs:\r\n"
str_ps_header_end:

str_pid_prefix:
	.ascii	"PID: "

str_dot:
	.asciz	"."

str_newline:
	.ascii	"\r\n"

str_klog_path:
	.asciz	"/dev/klog"

str_help_cmd:
	.asciz	"help"

str_ls_cmd:
	.asciz	"ls"

str_cat_cmd:
	.asciz	"cat"

str_ps_cmd:
	.asciz	"ps"

str_dmesg_cmd:
	.asciz	"dmesg"

str_uname_cmd:
	.asciz	"uname"

str_reboot_cmd:
	.asciz	"reboot"

str_exit_cmd:
	.asciz	"exit"

str_quit_cmd:
	.asciz	"quit"

str_exec_cmd:
	.asciz	"exec"
