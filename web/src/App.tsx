import AAIIIndicator from "./components/indicators/AAIIIndicator";
import CBDCIndicator from "./components/indicators/CBDCIndicator";
import TariffIndicator from "./components/indicators/TariffIndicator";
import OpenBBIndicatorGrid from "./components/indicators/OpenBBIndicatorGrid";

export default function App() {
  return (
    <div className="min-h-screen bg-canvas text-ink p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Nave Trading Dashboard</h1>

        {/* Market Sentiment Section */}
        <section className="mb-12">
          <h2 className="text-2xl font-bold mb-6">Market Sentiment</h2>
          <div className="grid gap-6 lg:grid-cols-2">
            <AAIIIndicator />
            <CBDCIndicator />
          </div>
        </section>

        {/* Economic Indicators Section */}
        <section className="mb-12">
          <OpenBBIndicatorGrid />
        </section>

        {/* Government & Policy Section */}
        <section className="mb-12">
          <h2 className="text-2xl font-bold mb-6">Government & Policy</h2>
          <div className="grid gap-6 lg:grid-cols-1">
            <TariffIndicator />
          </div>
        </section>
      </div>
    </div>
  );
}
