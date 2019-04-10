module.exports = async function(context, commands) {
  // This is perhaps not obvious, but it's all basically from
  // [the browsertime documentation](https://www.sitespeed.io/documentation/sitespeed.io/scripting/#pass-your-own-options-to-your-script).

  const webdriver = context.selenium.webdriver;
  const driver = context.selenium.driver;
  const oldContext = driver.getContext();

  try {
    await driver.setContext("chrome");

    // This example is GeckoView specific but the process and the API is not vehicle specific.  (It
    // is Firefox/Gecko specific, i.e., *it will not work in Chrome or Edge*.)
    const script = `
        console.log("This will be logged to the browsertime target console, i.e. to adb logcat.");
        const TelemetryGeckoView = Cc["@mozilla.org/telemetry/geckoview-testing;1"].createInstance(Ci.nsITelemetryGeckoViewTesting);
        TelemetryGeckoView.forcePersist();
        console.log("This will be logged to the browsertime target console, i.e. to adb logcat: " + typeof(TelemetryGeckoView));
    `;
    await driver.executeScript(script);
  } finally {
    await driver.setContext(oldContext);
  }

  console.log(`This will be logged to the browsertime host console: ${typeof(webdriver)}`);
  console.log(`This will be logged to the browsertime host console: ${typeof(driver)}`);

  // If you feel the need.
  // await commands.measure.start('https://www.sitespeed.io');

  // The above is equivalent to the following API that I added in the patch provided.
  const value = await commands.js.runPrivileged('const TelemetryGeckoView = Cc["@mozilla.org/telemetry/geckoview-testing;1"].createInstance(Ci.nsITelemetryGeckoViewTesting); return {"value": typeof(TelemetryGeckoView)}');
  console.log(`This will be logged to the browsertime host console: ${JSON.stringify(value)}`);

  // When I looked, it wasn't obvious how to inject additional measurements into the measurement
  // object _from this driver script_.  It's clear how to add measurements from _new_ scripts, but
  // not from right here.  I'll keep looking for this.
};
