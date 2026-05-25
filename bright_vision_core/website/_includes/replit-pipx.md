To use cecli with pipx on replit, you can run these commands in the replit shell:

```bash
pip install pipx
pipx run bright-vision-core ...normal cecli args...
```

If you install cecli with pipx on replit and try and run it as just `cecli` it will crash with a missing `libstdc++.so.6` library.

