// Populate ["browserScripts"]["privileged"]["privileged_Services.telemetry.getSnapshotForHistograms"].
(function() {
  "use strict";

  const {Services} = ChromeUtils.import("resource://gre/modules/Services.jsm");
  return Services.telemetry.getSnapshotForHistograms();
})();
