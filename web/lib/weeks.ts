/**
 * data/weeks/<week>.json 을 읽는다. 빌드 타임에만 호출된다 (정적 생성).
 *
 * ⚠️ **서버 전용이다.** `node:fs`를 쓰므로 클라이언트 컴포넌트에서 import하면
 * 빌드가 깨진다. 타입과 포맷터는 `lib/item.ts`에 있다 — 그쪽을 쓸 것.
 */
import fs from "node:fs";
import path from "node:path";

import { WEEK_PATTERN, type Week } from "@/lib/item";

// 타입과 포맷터는 여기서도 그대로 쓸 수 있게 다시 내보낸다.
export { WEEK_PATTERN, formatWeek, formatPrice } from "@/lib/item";
export type { Item, Week } from "@/lib/item";

const WEEKS_DIR = path.join(process.cwd(), "..", "data", "weeks");

/** 발행된 주차 목록, 최신순. `.report.json` 같은 부산물은 제외한다. */
export function listWeeks(): string[] {
  if (!fs.existsSync(WEEKS_DIR)) return [];
  return fs
    .readdirSync(WEEKS_DIR)
    .filter((f) => f.endsWith(".json") && !f.endsWith(".report.json"))
    .map((f) => f.replace(/\.json$/, ""))
    .filter((w) => WEEK_PATTERN.test(w))
    .sort()
    .reverse();
}

export function readWeek(week: string): Week | null {
  if (!WEEK_PATTERN.test(week)) return null;
  const file = path.join(WEEKS_DIR, `${week}.json`);
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Week;
}

export function latestWeek(): string | null {
  return listWeeks()[0] ?? null;
}
