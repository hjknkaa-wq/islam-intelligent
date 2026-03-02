# Oh My OpenCode Profiles

This project provides 3 local profiles for `oh-my-opencode`:

- `safe`: lowest autonomy and lowest parallelism.
- `balanced`: recommended default for daily use.
- `max-autonomy`: highest autonomy and aggressive parallelism.

## Switch profile

From project root:

```powershell
.\use-omo-profile.ps1 safe
.\use-omo-profile.ps1 balanced
.\use-omo-profile.ps1 max-autonomy
```

Optional:

```powershell
.\use-omo-profile.ps1 balanced -SkipDoctor
```

## Files

- Active config: `.opencode/oh-my-opencode.jsonc`
- Presets: `.opencode/profiles/*.jsonc`
