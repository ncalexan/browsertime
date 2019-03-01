# How to use browsertime for evaluating Firefox TV

1. Get Firefox TV onto your target:

```
git clone https://github.com/ncalexan/firefox-tv ncalexan-firefox-tv
cd ncalexan-firefox-tv
git checkout 9cf2b39d92378edc3aeeed441f835198018b3a1b
./gradlew app:installSystemDebug app:installGeckoDebug
```

My patches produce `org.mozilla.tv.firefox{.gecko}.debug` on the
device (as well as other things for automation).

2. Get browsertime onto your host:

```
git clone https://github.com/ncalexan/browsertime ncalexan-browsertime
cd ncalexan-browsertime
git checkout master
# Or at least c0813a288dda892c0125ee53855d00eae4fa469a.
npm install
```

That will prepare browsertime and include needed changes to
`selenium-webdriver` (which are vendored into that repository).

3. Build yourself a geckodriver with initial support for `android.*`
options.

```
hg clone https://hg.mozilla.org/mozilla-central
cd mozilla-central
hg pull https://hg.mozilla.org/users/nalexander_mozilla.com/gecko -r 8209adfbacba
cd testing/geckodriver
cargo build
```

That should produce a `target/debug/geckodriver` binary in your top
source directory.

4. Fetch chromedriver-2.32 (depends on your target device) from
https://chromedriver.storage.googleapis.com/index.html.

5. Consult the `one.sh` and `many.sh` scripts for new options, etc.
See `gve.js` for driving `geckodriver` from `selenium-webdriver`.

6. Note that you *must* set `ANDROID_SERIAL` in your environment:
`geckodriver` doesn't yet choose a device if you don't tell it which
one to use.
