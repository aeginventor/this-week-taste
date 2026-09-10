import { site, type Channel } from "@/config/site";
import { FilteredItems } from "@/components/FilteredItems";
import { formatWeek, type Week } from "@/lib/weeks";

function channelLabel(channel: string): string {
  return site.channels[channel as Channel] ?? channel;
}

/**
 * 한 주차 페이지. 머리말과 아카이브는 서버에서 그리고, 필터가 붙는 목록만
 * 클라이언트 컴포넌트에 넘긴다 (`FilteredItems`).
 */
export function WeekView({ data, weeks }: { data: Week; weeks: string[] }) {
  return (
    <div className="week">
      <div className="week-head">
        <h1>{formatWeek(data.week)} 발견 기록</h1>
        {weeks.length > 1 && (
          <nav className="archive">
            {weeks.map((w) => (
              <a key={w} href={`/week/${w}`}
                 className={w === data.week ? "current" : ""}>
                {formatWeek(w)}
              </a>
            ))}
          </nav>
        )}
      </div>

      <p className="note">
        제품 목록에서 새로 관측한 항목입니다. 발견한 주와 실제 출시 시점은 다를 수 있습니다.
        현재 기록의 공식 출시 사실과 시점은 확인되지 않았습니다.
      </p>
      {data.source_statuses && (
        <details className="note">
          <summary>출처별 수집 시점과 반영 상태</summary>
          <ul>
            {Object.entries(data.source_statuses).map(([source, state]) => (
              <li key={source}>
                {state.brand ?? data.items.find((item) => item.source_id === source)?.brand ?? source}: {state.status === "excluded"
                  ? "이번 발행에서 제외됨 — 자료 확인 필요"
                  : `${state.scraped_at ? new Date(state.scraped_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) + " (한국 시간) 수집" : "수집 시점 미상"}${state.status === "reused" ? " · 재처리 실패 후 검증된 이전 결과 유지" : ""}`}
              </li>
            ))}
          </ul>
        </details>
      )}
      <FilteredItems items={data.items} />

      <p className="channels">
        {Array.from(new Set(data.items.map((i) => i.channel))).map((c) => (
          <span key={c}>{channelLabel(c)}</span>
        ))}
      </p>
    </div>
  );
}
