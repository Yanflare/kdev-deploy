---
title: Custom System Information Gathering Alias
tags: system-information, alias, shell-function
complexity: low
summary: This skill adds a custom shell function alias to gather system information quickly.
---
## When to use
Use this when you need to regularly check system information such as CPU usage, memory status, and disk space.

## Approach
Integrate a predefined set of commands into a single shell function alias in your user profile preferences. Use `shell_exec` for executing the combined command in one go.

## Example
To add an alias named `sysinfo`, open your `.bashrc` or equivalent configuration file using `file_read`. Add the following line:
```shell
alias sysinfo='echo "System Information:" && hostname; echo -e "\nCPU Info:"; cat /proc/cpuinfo | head -n 5; echo -e "\nMemory Usage:"; free -m; echo -e "\nDisk Space:"; df -h'
```
Then, use `shell_exec` to run the alias and gather system information:
```shell
shell_exec("sysinfo")
```

## Pitfalls
Ensure that each command in your alias outputs relevant information concisely. Avoid commands that take long to execute or require user input.