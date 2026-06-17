# Release checklist (do this on your Windows PC)

Everything in this repo is ready to publish. Two steps can only be done by
you, on your machine. Both are quick.

## 1. Put the repo online (anonymous is fine)

You can stay pseudonymous: make a GitHub account under any name. The repo
proves what the code does without proving who you are.

1. Create a free account at https://github.com (use a pseudonym if you like).
2. Make a new PUBLIC repository, e.g. "blue-protocol-midi-player".
3. Upload every file in this folder EXCEPT the build output. The .gitignore
   already excludes build/, dist/, and .exe files, so if you use git it
   handles this for you. If you upload by hand on the website, just don't
   upload the build/ or dist/ folders or any .exe.
4. Copy your repo's URL and paste it into README.md where it says
   REPLACE-WITH-YOUR-REPO-URL, then commit that change.

WARNING: do not upload the build/ or dist/ folders. The intermediate build
files still contain your Windows username in internal paths (the scrubber
only cleans the final .exe). The .gitignore prevents this if you use git.

## 2. Publish the .exe with its hash

For each release:

1. Build a fresh exe by double-clicking build.bat. This produces
   dist\BlueProtocolPlayer.exe with your username already scrubbed.
2. Get its SHA-256 hash. Open PowerShell in the dist folder and run:

       Get-FileHash BlueProtocolPlayer.exe -Algorithm SHA256

3. On GitHub, go to your repo, click "Releases", then "Draft a new release".
4. Attach dist\BlueProtocolPlayer.exe as a release asset.
5. In the release notes, paste the SHA-256 value from step 2, labelled
   clearly, e.g.:

       SHA-256: <the long hex string>

   This lets anyone confirm the file they downloaded is the real one.

## Optional but nice

- Run a VirusTotal scan of the exe (https://www.virustotal.com), and link
  the result in the release notes with a one-line "these are PyInstaller
  false positives, see the README" so nobody panics.
- Pin a message wherever you share it (Discord, forum) saying the GitHub
  release is the ONLY official source.

That's it. After step 1 and 2 you have a publicly verifiable, source-available
release that people can read, rebuild, and hash-check.
