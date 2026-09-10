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
      <FilteredItems items={data.items} />

      <p className="channels">
        {Array.from(new Set(data.items.map((i) => i.channel))).map((c) => (
          <span key={c}>{channelLabel(c)}</span>
        ))}
      </p>
    </div>
  );
}
