import fs from 'fs';
import path from 'path';

export const DATA_DIR = '.konceptos';
export const STATE_FILE = 'state.json';
export const SNAPS_DIR = 'snapshots';

export function getDataPath() {
  return path.join(process.cwd(), DATA_DIR);
}

export function ensureDataDir() {
  const dp = getDataPath();
  if (!fs.existsSync(dp)) fs.mkdirSync(dp, { recursive: true });
  const sp = path.join(dp, SNAPS_DIR);
  if (!fs.existsSync(sp)) fs.mkdirSync(sp, { recursive: true });
  return dp;
}

export function loadState() {
  const fp = path.join(process.cwd(), DATA_DIR, STATE_FILE);
  if (fs.existsSync(fp)) {
    try {
      return JSON.parse(fs.readFileSync(fp, 'utf8'));
    } catch {}
  }
  return null;
}

export function saveState(state) {
  ensureDataDir();
  const fp = path.join(getDataPath(), STATE_FILE);
  fs.writeFileSync(fp, JSON.stringify(state, null, 2));
}

export function saveSnapshot(state, snapIndex) {
  ensureDataDir();
  const fp = path.join(getDataPath(), SNAPS_DIR, `${snapIndex}.json`);
  fs.writeFileSync(fp, JSON.stringify(state, null, 2));
}

export function loadSnapshot(index) {
  const fp = path.join(getDataPath(), SNAPS_DIR, `${index}.json`);
  if (fs.existsSync(fp)) {
    return JSON.parse(fs.readFileSync(fp, 'utf8'));
  }
  return null;
}
