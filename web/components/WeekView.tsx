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
        <h1>{formatWeek(data.week)} 신상</h1>
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

      <FilteredItems items={data.items} />

      <p className="channels">
        {Array.from(new Set(data.items.map((i) => i.channel))).map((c) => (
          <span key={c}>{channelLabel(c)}</span>
        ))}
      </p>
    </div>
  );
}
