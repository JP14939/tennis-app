# Expo HAS CHANGED

This project is on **Expo SDK 54** (`expo@54.0.x` — check
`frontend/package.json`). It is not on any newer SDK, and nothing here should
be written against one.

Read the exact versioned docs at https://docs.expo.dev/versions/v54.0.0/
before writing any code.

Two things that are specifically true on SDK 54 and easy to get wrong:

- **`expo-av` is deprecated on 54 and removed in SDK 55**, but this app still
  uses it deliberately (`components/PlatformVideo.native.js` for Video,
  `utils/sounds.js` for Audio). Don't "helpfully" migrate it — the move to
  `expo-video`/`expo-audio` is tracked as a deferred item in `TODO_MANUAL.md`
  and belongs with the SDK 55 upgrade.
- `app.json` deliberately has **no `sdkVersion` field**. Modern Expo infers it
  from the installed `expo` package; adding one back re-introduces a second
  source of truth that can drift.
