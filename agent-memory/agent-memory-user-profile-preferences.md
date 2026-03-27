# System Information Gathering Aliases and Functions

## Shell Aliases and Functions in User Profile Preferences

To quickly gather system information without typing out commands like `uname`, `hostname`, or `lscpu` each time, you can add the following aliases and functions to your user profile preferences.

### Alias for Quick Kernel Info
```sh
alias sysinfo='uname -a'
```

This alias will execute the command `uname -a` which provides comprehensive system information including kernel name, version, hardware name, machine type, processor type, hardware platform, operating system, and release details.

### Function to Show Hostname with Domain Name
```sh
function show_hostname {
  shell_exec 'hostname'
}
```

The function `show_hostname` uses the KDEV tool `shell_exec` to execute the command `hostname`, which displays the hostname of your machine. If a domain name is defined in `/etc/hosts`, it will also display that.

### Function for CPU Information
```sh
function cpu_info {
  shell_exec 'lscpu'
}
```

The function `cpu_info` uses `shell_exec` to run the command `lscpu`. This provides detailed information about your CPU architecture, such as vendor ID, CPU family, model name, number of threads per core, and more.

By adding these commands into your user profile preferences file (such as `.bashrc`, `.zshrc`, etc.), you can quickly gather essential system details with just one command or function call.