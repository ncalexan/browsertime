// Licensed to the Software Freedom Conservancy (SFC) under one
// or more contributor license agreements.  See the NOTICE file
// distributed with this work for additional information
// regarding copyright ownership.  The SFC licenses this file
// to you under the Apache License, Version 2.0 (the
// "License"); you may not use this file except in compliance
// with the License.  You may obtain a copy of the License at
//
//   http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an
// "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
// KIND, either express or implied.  See the License for the
// specific language governing permissions and limitations
// under the License.

/**
 * @fileoverview A basic example of working with a GeckoView-consuming
 * App on Android. Before running this example, you must start adb and
 * connect a device (or start an AVD).
 */

'use strict';

const {Builder, By, Key, promise, until} = require('selenium-webdriver');
const {Options, ServiceBuilder, setDefaultService} = require('selenium-webdriver/firefox');

let geckodriverPath = '/Users/nalexander/Mozilla/gecko/target/debug/geckodriver';
let serviceBuilder = new ServiceBuilder(geckodriverPath);
// if (options.verbose >= 2) {
//   // This echoes the output from geckodriver to the console.
serviceBuilder.setStdio('inherit');
//   // TODO: serviceBuilder.loggingTo(`${baseDir}/geckodriver.log`);
//   if (options.verbose >= 3)
serviceBuilder.enableVerboseLogging();
// }
setDefaultService(serviceBuilder.build());

promise.consume(function* () {
  let driver;
  try {
    driver = yield new Builder()
        .forBrowser('firefox')
        .setFirefoxOptions(
          new Options()
            .androidAddIntentArguments('--ez', 'TURBO_MODE', 'false')
            .androidAddIntentArguments('-a', 'android.intent.action.VIEW', '-d', 'https://example.com')
            .androidPackage('org.mozilla.tv.firefox.gecko.debug')
            .androidActivity('org.mozilla.tv.firefox.MainActivity'))
        .build();

    yield driver.get('http://www.google.com/ncr');
    yield driver.wait(until.titleIs('Google'), 2000);
    yield driver.findElement(By.name('q')).sendKeys('webdriver', Key.RETURN);
    yield driver.wait(until.titleIs('webdriver - Google Search'), 2000);
  } finally {
    yield driver && driver.quit();
  }
}).then(_ => console.log('SUCCESS'), err => console.error('ERROR: ' + err));
