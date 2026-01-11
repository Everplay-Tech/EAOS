#!/bin/bash
# Pipe code to Ork for review
echo "Analyzing code with Ork..."
cat $1 | ork call "Review this file system code for bugs and optimization:"
