import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Zap, TrendingUp } from "lucide-react";
import { api } from "../services/api";
import { StatsCard } from "./StatsCard";
import { LiveFeed } from "./LiveFeed";

export const Dashboard: React.FC = () => {
  const { data: summary, isLoading } = useQuery({
    queryKey: ["summary"],
    queryFn: api.getSummary,
    refetchInterval: 100000000000, // Refresh every 30s
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-3xl font-bold text-gray-900">
            Smart Meter Dashboard
          </h1>
          <p className="text-gray-600 mt-1">
            Real-time monitoring with blockchain integration
          </p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatsCard
            title="Total Readings"
            value={summary?.total_readings || 0}
            icon={Activity}
            color="blue"
          />
          <StatsCard
            title="Active Meters"
            value={summary?.total_meters || 0}
            icon={Zap}
            color="green"
          />
          <StatsCard
            title="Suspicious Readings"
            value={summary?.total_suspicious || 0}
            icon={AlertTriangle}
            color="red"
          />
          <StatsCard
            title="Success Rate"
            value={`${(
              ((summary?.successful_requests || 0) /
                (summary?.total_requests || 1)) *
              100
            ).toFixed(1)}%`}
            icon={TrendingUp}
            color="purple"
          />
        </div>

        {/* Live Feed */}
        <LiveFeed />
      </main>
    </div>
  );
};
