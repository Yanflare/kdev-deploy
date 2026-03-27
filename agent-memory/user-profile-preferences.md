---
title: Custom Shell Function for Quick File Listing
tags: shell, ls, productivity
complexity: low
summary: Adds a custom shell function to quickly list files with detailed information.
---
## When to use
Use this skill when you frequently need to check file details in your directory and prefer a quick command to do so.

## Approach
Create a custom shell function named `l` that uses the `ls` command with `-alh` options for a more detailed view of files. This can be added directly into the user profile preferences.

## Example
```shell
function l() { ls -alh "$@"; }
```
This example demonstrates how to define and use the custom function in your shell session.

## Pitfalls
Ensure that the new alias does not conflict with existing commands or aliases. Also, verify that the `ls` command is available in your environment.
alias np='ping'
alias nt='traceroute'
function l() { ls -alh "$@"; }