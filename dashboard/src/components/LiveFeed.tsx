import { useState } from "react";
import { Activity, AlertTriangle } from "lucide-react";
import { useReadingsSSE, useAlertsSSE } from "../services/sse";
import { formatTimestamp, getSeverityColor } from "../utils/helper";
import type { Reading, Alert } from "../types";

export const LiveFeed: React.FC = () => {
  const [readings, setReadings] = useState<Reading[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  const { connected: readingsConnected } = useReadingsSSE((reading) => {
    setReadings((prev) => [reading, ...prev].slice(0, 10));
  });

  const { connected: alertsConnected } = useAlertsSSE((alert) => {
    setAlerts((prev) => [alert, ...prev].slice(0, 10));
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Recent Readings */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-600" />
            <h3 className="text-lg font-semibold">Live Readings</h3>
          </div>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                readingsConnected ? "bg-green-500" : "bg-red-500"
              }`}
            />
            <span className="text-sm text-gray-500">
              {readingsConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>
        <div className="p-6">
          {readings.length === 0 ? (
            <p className="text-gray-500 text-center py-8">
              Waiting for readings...
            </p>
          ) : (
            <div className="space-y-3">
              {readings.map((reading, idx) => (
                <div
                  key={`${reading.meterID}-${reading.seq}`}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded"
                >
                  <div>
                    <p className="font-medium">{reading.meterID}</p>
                    <p className="text-sm text-gray-600">
                      Seq: {reading.seq} | Value: {reading.value.toFixed(2)} kWh
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-500">
                      {formatTimestamp(reading.ts)}
                    </p>
                    {reading.suspicious === 1 && (
                      <span
                        className={`text-xs px-2 py-1 rounded ${getSeverityColor(
                          reading.score
                        )}`}
                      >
                        Suspicious
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent Alerts */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-600" />
            <h3 className="text-lg font-semibold">Live Alerts</h3>
          </div>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                alertsConnected ? "bg-green-500" : "bg-red-500"
              }`}
            />
            <span className="text-sm text-gray-500">
              {alertsConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>
        <div className="p-6">
          {alerts.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No alerts detected</p>
          ) : (
            <div className="space-y-3">
              {alerts.map((alert, idx) => (
                <div
                  key={`${alert.meterID}-${alert.seq}`}
                  className="p-3 bg-red-50 border border-red-200 rounded"
                >
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-medium text-red-900">{alert.meterID}</p>
                    <span
                      className={`text-xs px-2 py-1 rounded ${getSeverityColor(
                        alert.score
                      )}`}
                    >
                      Score: {alert.score.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700">
                    Reasons: {alert.reasons.join(", ")}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    {formatTimestamp(alert.ts)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
