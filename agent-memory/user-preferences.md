---
title: Add Custom Shell Function for Quick Process Monitoring in User Preferences
tags: process-monitoring, user-preferences, shell-functions
complexity: low
summary: Adds a custom shell function to the user's profile preferences for quick system process monitoring using KDEV tools.
---
## When to use
When a user needs a convenient way to monitor processes on their system through an alias or function that simplifies command usage.

## Approach
Use `shell_exec` to create and add a custom shell function named `psmon` to the user's `.bashrc` or `.zshrc`. This function will execute a process monitoring command, providing quick insights into running processes using KDEV tools. The example provided uses `ssh_exec` to fetch and display process information from another system.

## Example
To add the custom shell function for process monitoring:
```shell
function psmon() {
  ssh_exec "ps aux | grep $1"
}
```
This function allows users to quickly monitor processes by executing a command similar to `psmon [process_name]`.

## Pitfalls
- Ensure that the function name is unique and does not conflict with existing commands.
- Users should source their shell configuration file (`source ~/.bashrc`) after adding new functions to apply them without logging out.