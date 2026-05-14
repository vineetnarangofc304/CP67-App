#!/usr/bin/env node
/*
 * Non-interactive Bubblewrap bootstrap for CP67 Mall.
 *
 * - Reads the live PWA manifest
 * - Generates twa-manifest.json with hard-coded answers
 * - Generates the Android project files
 * - Creates a signing keystore (deterministic creds)
 * - Writes manifest-checksum.txt so subsequent `bubblewrap build` runs cleanly
 */
const path = require('path');
const fs = require('fs');

const CORE_PATH = '/usr/lib/node_modules/@bubblewrap/cli/node_modules/@bubblewrap/core';
const CLI_PATH = '/usr/lib/node_modules/@bubblewrap/cli';

const {
  TwaManifest,
  TwaGenerator,
  JdkHelper,
  KeyTool,
  Config,
  ConsoleLog,
  BufferedLog,
} = require(CORE_PATH);

const { computeChecksum } = require(path.join(CLI_PATH, 'dist/lib/cmds/shared.js'));

const MANIFEST_URL = process.env.MANIFEST_URL || 'https://cp67bot.fundlexperiences.com/manifest.json';
const TARGET_DIR = process.env.TARGET_DIR || '/app/twa-build';

const PACKAGE_ID = 'com.fundle.cp67';
const APP_NAME = 'CP67 Mall';
const LAUNCHER_NAME = 'CP67 Mall';
const VERSION_CODE = 1;
const KEYSTORE_PASSWORD = process.env.BUBBLEWRAP_KEYSTORE_PASSWORD || 'CP67Mall@2025';
const KEY_PASSWORD = process.env.BUBBLEWRAP_KEY_PASSWORD || 'CP67Mall@2025';

(async () => {
  const log = new ConsoleLog('cp67-bootstrap');

  log.info(`Fetching web manifest from ${MANIFEST_URL}`);
  let twaManifest = await TwaManifest.fromWebManifest(MANIFEST_URL);

  // Hard-code answers that `bubblewrap init` would otherwise prompt for.
  twaManifest.packageId = PACKAGE_ID;
  twaManifest.name = APP_NAME;
  twaManifest.launcherName = LAUNCHER_NAME;
  twaManifest.appVersionCode = VERSION_CODE;
  twaManifest.appVersionName = String(VERSION_CODE);
  twaManifest.signingKey = {
    path: path.join(TARGET_DIR, 'android.keystore'),
    alias: 'android',
  };
  // Keep the generated host/icons/colors/displayMode/orientation from the web manifest.

  // Validate.
  const error = twaManifest.validate();
  if (error) throw new Error('Invalid TWA Manifest: ' + error);

  if (!fs.existsSync(TARGET_DIR)) fs.mkdirSync(TARGET_DIR, { recursive: true });

  // Save twa-manifest.json
  const manifestFile = path.join(TARGET_DIR, 'twa-manifest.json');
  await twaManifest.saveToFile(manifestFile);
  log.info('Saved twa-manifest.json');

  // Generate Android project
  const twaGenerator = new TwaGenerator();
  const bufLog = new BufferedLog(new ConsoleLog('twa-gen'));
  await twaGenerator.createTwaProject(TARGET_DIR, twaManifest, bufLog, () => {});
  bufLog.flush();
  log.info('Android project scaffolded');

  // Compute & save manifest checksum so build doesn't try to re-prompt
  const sum = computeChecksum(await fs.promises.readFile(manifestFile));
  await fs.promises.writeFile(path.join(TARGET_DIR, 'manifest-checksum.txt'), sum);
  log.info('Wrote manifest-checksum.txt');

  // Create the signing key
  const config = new Config('/usr/lib/jvm/java-17-openjdk-arm64', '/root/.bubblewrap/androidSdk');
  const jdkHelper = new JdkHelper(process, config);
  const keytool = new KeyTool(jdkHelper);

  if (!fs.existsSync(twaManifest.signingKey.path)) {
    await keytool.createSigningKey({
      fullName: 'Bharat Sharma',
      organizationalUnit: 'Homeland Advantage',
      organization: 'CP67 Mall',
      country: 'IN',
      password: KEYSTORE_PASSWORD,
      keypassword: KEY_PASSWORD,
      alias: twaManifest.signingKey.alias,
      path: twaManifest.signingKey.path,
    });
    log.info('Signing key created');
  } else {
    log.info('Signing key already exists, skipping creation');
  }

  log.info('Bootstrap complete. Run `bubblewrap build --skipPwaValidation` next.');
})().catch((err) => {
  console.error('Bootstrap failed:', err);
  process.exit(1);
});
