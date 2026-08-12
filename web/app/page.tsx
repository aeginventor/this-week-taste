import { WeekView } from "@/components/WeekView";
import { latestWeek, listWeeks, readWeek } from "@/lib/weeks";

export default function HomePage() {
  const week = latestWeek();
  const data = week ? readWeek(week) : null;

  if (!data) {
    // 발행된 주차가 없다. 조용히 빈 페이지를 내보내지 않고 그 사실을 말한다 (CLAUDE.md 2.4).
    return (
      <div className="empty">
        <h1>아직 발행된 주차가 없습니다</h1>
        <p>
          <code>data/weeks/</code> 에 발행 파일이 없습니다. 파이프라인을 먼저
          실행하세요: <code>make week</code>
        </p>
      </div>
    );
  }

  return <WeekView data={data} weeks={listWeeks()} />;
}
