import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../services/api";
import {
  getSeverityColor,
  getSeverityLabel,
  formatTimestamp,
  formatRelativeTime,
} from "../utils/helper";
import type { Alert } from "../types";
import { AlertTriangle, Filter } from "lucide-react";

export const AlertList: React.FC = () => {
  const [minScore, setMinScore] = useState(0.4);
  const [meterFilter, setMeterFilter] = useState("");
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["alerts", minScore, meterFilter],
    queryFn: () =>
      api.getAlerts({
        min_score: minScore,
        meterID: meterFilter || undefined,
        limit: 50,
        offset: 0,
      }),
    refetchInterval: 15000,
  });

  const alerts = (data || []) as Alert[];

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-red-600" />
          <h3 className="text-lg font-semibold">Alerts</h3>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <input
              value={meterFilter}
              onChange={(e) => setMeterFilter(e.target.value)}
              placeholder="Filter by meterID"
              className="border rounded px-2 py-1 text-sm"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">Min score</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.1}
              value={minScore}
              onChange={(e) => setMinScore(parseFloat(e.target.value))}
              className="w-20 border rounded px-2 py-1 text-sm"
            />
          </div>
          <button onClick={() => refetch()} className="text-sm text-blue-600">
            Refresh
          </button>
        </div>
      </div>

      <div className="p-6">
        {isLoading ? (
          <p className="text-gray-500">Loading...</p>
        ) : alerts.length === 0 ? (
          <p className="text-gray-500">No alerts for current filter.</p>
        ) : (
          <div className="space-y-3">
            {alerts.map((a) => (
              <div
                key={`${a.meterID}-${a.seq}`}
                className="p-3 bg-red-50 border border-red-200 rounded"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-red-900">{a.meterID}</p>
                    <p className="text-xs text-gray-600">Seq: {a.seq}</p>
                  </div>
                  <div className="text-right">
                    <span
                      className={`text-xs px-2 py-1 rounded ${getSeverityColor(
                        a.score
                      )}`}
                    >
                      {getSeverityLabel(a.score)} ({a.score.toFixed(2)})
                    </span>
                    <p className="text-xs text-gray-500 mt-1">
                      {formatTimestamp(a.ts)} · {formatRelativeTime(a.ts)}
                    </p>
                  </div>
                </div>
                {a.reasons?.length > 0 && (
                  <p className="text-sm text-gray-700 mt-2">
                    Reasons: {a.reasons.join(", ")}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
