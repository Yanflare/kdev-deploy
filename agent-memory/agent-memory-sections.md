---
title: Quick Disk Space Listing Function
tags: disk-space, shell-function, system-administration
complexity: low
summary: Adds a custom shell function to quickly list disk space usage.
---
## When to use
When you need a quick overview of your disk space usage without running multiple commands manually.

## Approach
Integrate a shell function that uses `shell_exec` to run the command `df -h` and print the output in an easy-to-read format directly within your shell session.

## Example
```sh
# Add this line to your .bashrc or .zshrc file
function disk_usage() {
  shell_exec "df -h"
}
```
After adding, reload your profile with `source ~/.bashrc` (or `.zshrc`) and use the function by simply typing `disk_usage`.

## Pitfalls
Ensure that the function name does not conflict with existing aliases or functions. If you encounter an issue where `shell_exec` is not recognized, make sure it’s sourced correctly from your profile file.