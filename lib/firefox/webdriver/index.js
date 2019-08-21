'use strict';

const path = require('path');
const firefox = require('selenium-webdriver/firefox');
const proxy = require('selenium-webdriver/proxy');
const pick = require('lodash.pick');
const isEmpty = require('lodash.isempty');
const log = require('intel').getLogger('browsertime.firefox');
const util = require('../../support/util');
const get = require('lodash.get');
const defaultFirefoxPreferences = require('./firefoxPreferences');

module.exports.configureBuilder = function(builder, baseDir, options) {
  const firefoxConfig = options.firefox || {};
  const moduleRootPath = path.resolve(__dirname, '..', '..', '..');
  const ffOptions = new firefox.Options();

  let geckodriverPath = get(
    firefoxConfig,
    'geckodriverPath'
  );
  if (!geckodriverPath) {
    const geckodriver = require('@sitespeed.io/geckodriver');
    geckodriverPath = geckodriver.binPath();
  }

  // Other implementations configure the Web Driver service only once.
  // However, `selenium-webdriver` fixes a port for `geckodriver` when
  // the service is built, but in between browsertime iterations the
  // port is not held.  That means the OS can allocate it, and indeed
  // collisions are frequent in the wild.  By configuring the Web
  // Driver service, we fix a new port for `geckodriver` each
  // iteration, avoiding port collisions.
  let serviceBuilder = new firefox.ServiceBuilder(geckodriverPath);
  if (options.verbose >= 2) {
    // This echoes the output from geckodriver to the console.
    serviceBuilder.setStdio('inherit');
    // TODO: serviceBuilder.loggingTo(`${baseDir}/geckodriver.log`);
    if (options.verbose >= 3) {
      serviceBuilder.enableVerboseLogging();
    }
  }
  firefox.setDefaultService(serviceBuilder.build());

  const profileTemplatePath = get(
    firefoxConfig,
    'profileTemplate',
    path.resolve(
      moduleRootPath,
      'browsersupport',
      'firefox-profile'
    )),
    profile = new firefox.Profile(profileTemplatePath);

  if (options.userAgent) {
    ffOptions.setPreference('general.useragent.override', options.userAgent);
  }

  if (firefoxConfig.collectMozLog) {
    process.env.MOZ_LOG =
      'timestamp,nsHttp:5,cache2:5,nsSocketTransport:5,nsHostResolver:5';
    process.env.MOZ_LOG_FILE = `${baseDir}/moz_log.txt`;
  }

  // Output the window recorder image frames to a base directory.
  // This pref expects a trailing slash.
  if (firefoxConfig.windowRecorder) {
    profile.setPreference('layers.windowrecording.path', path.join(baseDir,'/'));
  }

  // try to remove the caching between runs
  /*
   profile.setPreference('dom.enable_resource_timing', true);
   */
  Object.keys(defaultFirefoxPreferences).forEach(function(pref) {
    ffOptions.setPreference(pref, defaultFirefoxPreferences[pref]);
  });

  if (!options.skipHar) {
    // Hack for opening the toolbar
    // In Firefox 61 we need to have devtools open but do not need to choose netmonitor
    ffOptions.setPreference('devtools.toolbox.selectedTool', 'netmonitor');
    ffOptions.setPreference('devtools.toolbox.footer.height', 0);

    ffOptions.addExtensions(
      path.resolve(
        moduleRootPath,
        'vendor',
        'har_export_trigger-0.6.0-an+fx.xpi'
      )
    );
  }

  // Browsertime own extension
  ffOptions.addExtensions(
    path.resolve(moduleRootPath, 'vendor', 'browsertime-0.18.0-an+fx.xpi')
  );

  if (options.extension) {
    const extensions = !Array.isArray(options.extension)
      ? [options.extension]
      : options.extension;
    for (const extension of extensions) {
      ffOptions.addExtension(extension);
    }
  }

  ffOptions.setPreference('devtools.chrome.enabled', true);

  const userPrefs = util.toArray(firefoxConfig.preference);
  for (const pref of userPrefs) {
    const nameAndValue = pref.split(':');
    if (nameAndValue.length === 2) {
      const value =
        nameAndValue[1] === 'false'
          ? false
          : nameAndValue[1] === 'true'
          ? true
          : nameAndValue[1];
      // Firefox handles 0, "0", false differently. Turning of OSCP
      // security.OCSP.enabled:0
      // Only accepts a zero as integer
      if (isNaN(value)) {
        ffOptions.setPreference(nameAndValue[0], value);
      } else {
        ffOptions.setPreference(nameAndValue[0], Number(value));
      }
    } else {
      log.error(
        'Firefox preferences %s need to of the format key:value, preference was not set',
        pref
      );
    }
  }

  let firefoxTypes = [
    get(firefoxConfig, 'binaryPath')
      ? get(firefoxConfig, 'binaryPath')
      : undefined,
    get(firefoxConfig, 'nightly') ? firefox.Channel.NIGHTLY : undefined,
    get(firefoxConfig, 'beta') ? firefox.Channel.BETA : undefined,
    get(firefoxConfig, 'developer') ? firefox.Channel.AURORA : undefined
  ];

  firefoxTypes = firefoxTypes.filter(function(n) {
    return n !== undefined;
  });

  ffOptions.setBinary(
    firefoxTypes.length > 0 ? firefoxTypes[0] : firefox.Channel.RELEASE
  );

  ffOptions.addArguments('-no-remote');

  // Another hack for opening devtools to make netmonitor work
  if (!options.skipHar) {
    ffOptions.addArguments('-devtools');
  }

  if (options.headless) {
    ffOptions.headless();
  }

  const proxySettings = pick(options.proxy, ['http', 'https']);

  if (!isEmpty(proxySettings)) {
    let seleniumProxySettings = proxy.manual(proxySettings);
    seleniumProxySettings.httpProxyPort = proxySettings.http.split(':')[1];
    seleniumProxySettings.sslProxyPort = proxySettings.https.split(':')[1];
    ffOptions.setProxy(seleniumProxySettings);
  }

  if (firefoxConfig.acceptInsecureCerts) {
    builder.getCapabilities().set('acceptInsecureCerts', true);
  }

  builder
    .getCapabilities()
    .set('pageLoadStrategy', get(options, 'pageLoadStrategy', 'normal'));

  const android = firefoxConfig.android;
  if (android) {
    // Monkey patch to avoid changing `selenium-webdriver` before the
    // corresponding `geckodriver` functionality has been replaced:
    // see this [Firefox bug](https://bugzilla.mozilla.org/show_bug.cgi?id=1525126)
    // currently under review.
    if (android.package) {
      ffOptions.firefoxOptions_().androidPackage = android.package;
      if (android.activity) {
        ffOptions.firefoxOptions_().androidActivity = android.activity;
      }
    } else {
      ffOptions.firefoxOptions_().androidPackage = 'org.mozilla.firefox';
      ffOptions.firefoxOptions_().androidActivity = '.App';
    }
    ffOptions.firefoxOptions_().androidDeviceSerial = android.deviceSerial;
    ffOptions.firefoxOptions_().androidIntentArguments = (ffOptions.firefoxOptions_().androidIntentArguments || []).concat(...util.toArray(android.intentArgument));
  }

  builder.setFirefoxOptions(ffOptions);
};
