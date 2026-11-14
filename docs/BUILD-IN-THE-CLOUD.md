# Build both editions without a Mac

The **Build HaloPad (both editions, from your game files)** workflow builds HaloPad with the
Xbox edition *and* Halo Custom Edition on GitHub's free Apple silicon Mac computers. It runs the
same builder PadMint runs on a Mac (`scripts/builder/build.sh`), so you only need a web browser.

> [!NOTE]
> This route is new. Its tools check (Xcode, Homebrew tools, Wine, winetricks and a 32-bit Windows
> program under Wine) passes on GitHub's Mac, but a full both-editions build there has not yet been
> run with real game files. If yours fails, the step's log says where.

Only want the Xbox edition? Use **Build HaloPad (Xbox edition)** instead
([steps](../README.md#on-windows-linux-or-any-computer)). It needs no game files at all: you add
your disc inside the app.

## Why secrets, and why a password

Your fork is public, like this repository, so your game files must never be committed to it.
Instead you give the workflow three **repository secrets**. GitHub never shows a secret's value
to anyone, including in the run's log.

The finished app contains translated Halo code, your game files and your product ID. Anyone signed
in to GitHub can download a public repository's run artifacts, so the workflow locks everything in
a `.7z` archive with your password before saving it. Without the password the archive is unreadable;
even the file names are hidden.

## What you need

- Your **Halo Custom Edition 1.00 installer**, `HaloCESetup.exe` (the original installer, not the
  1.10 update patch). The workflow checks it against the same checksum PadMint uses.
- Your **Halo PC product key**.
- A free GitHub account with a fork of this repository.
- To play Custom Edition on **iPhone or iPad**, a way to sign the IPA. Custom Edition reserves Halo's
  full 32-bit address space, so sign with an Apple development profile that allows **Extended Virtual
  Addressing** and **Increased Memory Limit** ([install guide](INSTALL-IPHONE.md)). A free Apple ID
  in Sideloadly may be enough for the Xbox edition but has not been shown to run Custom Edition.
  The **Mac** build needs no Apple account.

## One-time setup

1. **Put your installer online privately.** Upload `HaloCESetup.exe` to Google Drive or Dropbox and
   create a share link that works for **anyone with the link** (the workflow cannot sign in). Share
   links from those two services are turned into direct downloads for you; any other direct download
   link works too. You may upload a `.zip` or `.7z` (without a password) holding the installer instead,
   optionally with `haloce-patch-1.0.10.exe` beside it. Otherwise the workflow downloads Bungie's free
   1.10 update itself.
2. In your fork on GitHub, open **Settings › Secrets and variables › Actions** and choose
   **New repository secret** three times:

   | Name | Value |
   | --- | --- |
   | `HALOCE_SETUP_URL` | The share link from step 1 |
   | `HALO_PRODUCT_KEY` | Your product key, `XXXXX-XXXXX-XXXXX-XXXXX-XXXXX` |
   | `HALOPAD_BUILD_PASSWORD` | A new password of 12 or more characters. You need it to open your build |

3. Open **Actions** and enable workflows if GitHub asks.

## Build

1. Open **Actions › Build HaloPad (both editions, from your game files) › Run workflow**.
2. Choose **iPhone and iPad** (an IPA) or **Mac**, then **Run workflow**.
   - Optional: tick **Only test the Mac tools and Wine** first. That run uses no game files or
     secrets and finishes in about 7 minutes.
3. Wait. Each run translates Halo and its DLLs and builds the Xbox engine from scratch on GitHub's
   free Mac (3 cores, 7 GB of memory), so it takes much longer than the 15-minute Xbox-only build;
   expect a few hours. The run stops after 5 hours 40 minutes. Nothing carries over between runs.
4. Open the finished run and download its artifact (kept for 7 days). It holds one `.7z` archive.
5. Open the archive with your `HALOPAD_BUILD_PASSWORD`: [7-Zip](https://www.7-zip.org) on Windows,
   Keka on a Mac or `7z x` on Linux. Inside are:
   - `HaloPad-v….ipa` (or the Mac app's `.zip`), the app
   - `Halo-CE.halopad.zip`, your Custom Edition game package
   - `READ-ME-FIRST.txt` and `SHA256SUMS`

## Install and play

**iPhone or iPad:** sign and install the IPA over any HaloPad you already have (never delete HaloPad
first: that deletes your saves). Copy `Halo-CE.halopad.zip` to the device with the Files app. Open
HaloPad, choose **Custom Edition**, then **Choose Prepared Package…** and pick it. For the Xbox edition,
choose **Add Your Xbox Disc** and pick your `.iso` or `.xiso`.

**Mac:** unzip the app and open it. Choose **Custom Edition**, then **Choose Prepared Package…** and pick
`Halo-CE.halopad.zip`.

**Your build is yours alone.** Never share the archive, its password, the app or the game package.

## Updating

Press **Sync fork** on your fork, run the workflow again with the same secrets, and install the new
app over the old one. Use the game package from the same run as the app.

## If the run fails

The failing step's log says what to fix. The log never contains your secrets.

| Step | Usual cause |
| --- | --- |
| Check your build secrets | A secret is missing, the key is not 25 letters and digits, or the password is under 12 characters |
| Download and verify your installer | The link needs "anyone with the link" access, points to a web page or folder, or the file is not the original 1.00 installer |
| Check Wine before the long build | A problem with GitHub's Mac or the Wine download; run again later |
| Build HaloPad with both editions | Report it with the log, without attaching any game files or your build |

You can remove the installer from Google Drive or Dropbox after a successful build, and delete the
secrets afterward. Add them again before your next build.
