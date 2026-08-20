
class MarketProfile:

    def build_tpo_profile(self, bars, price_increment):
        tpo_bins = {}

        for bar in bars:
            low = bar["low"]
            high = bar["high"]

            price = low
            while price <= high:
                bucket = round(price / price_increment) * price_increment
                tpo_bins[bucket] = tpo_bins.get(bucket, 0) + 1
                price += price_increment

        return tpo_bins


# Backwards-compatibility alias — imported as MarketProfileCalculator elsewhere in the pipeline
MarketProfileCalculator = MarketProfile
