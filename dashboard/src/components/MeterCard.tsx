import { Clipboard, CheckCircle2, AlertCircle, Activity } from "lucide-react";
import { useState } from "react";
import type { Meter } from "../types";
import { formatRelativeTime } from "../utils/helper";

interface Props {
  meter: Meter;
  onClick?: (meterID: string) => void;
}

export const MeterCard: React.FC<Props> = ({ meter, onClick }) => {
  const [copied, setCopied] = useState(false);
  const online =
    !!meter.last_update && Date.now() / 1000 - (meter.last_update || 0) < 120;

  const copy = async () => {
    await navigator.clipboard.writeText(meter.meterID);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      className="bg-white rounded-lg shadow p-4 hover:shadow-md transition cursor-pointer"
      onClick={() => onClick?.(meter.meterID)}
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="font-semibold truncate">{meter.meterID}</p>
          <p className="text-xs text-gray-500">
            Last seq: {meter.last_seq} ·{" "}
            {meter.last_update
              ? formatRelativeTime(meter.last_update)
              : "no data"}
          </p>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            copy();
          }}
          className="p-1 text-gray-500 hover:text-gray-700"
        >
          {copied ? (
            <CheckCircle2 className="w-4 h-4 text-green-600" />
          ) : (
            <Clipboard className="w-4 h-4" />
          )}
        </button>
      </div>

      <div className="flex items-center gap-3 mt-3">
        <span
          className={`text-xs px-2 py-1 rounded ${
            online ? "text-green-700 bg-green-100" : "text-gray-600 bg-gray-100"
          }`}
        >
          {online ? "Online" : "Offline"}
        </span>
        <span className="text-xs px-2 py-1 rounded text-blue-700 bg-blue-100 flex items-center gap-1">
          <Activity className="w-3 h-3" /> {meter.total_readings} readings
        </span>
        <span
          className={`text-xs px-2 py-1 rounded ${
            meter.recent_suspicious_count > 0
              ? "text-red-700 bg-red-100"
              : "text-green-700 bg-green-100"
          }`}
        >
          {meter.recent_suspicious_count > 0 ? (
            <>
              {" "}
              <AlertCircle className="w-3 h-3 inline" />{" "}
              {meter.recent_suspicious_count} suspicious{" "}
            </>
          ) : (
            "No suspicious"
          )}
        </span>
      </div>

      <div className="mt-2 text-xs text-gray-600">
        Avg score: {meter.average_score.toFixed(2)}
      </div>
    </div>
  );
};
