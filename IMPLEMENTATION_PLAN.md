# Custom Subscription Pricing Implementation Plan

## Overview
Allow users to choose their own subscription amount and billing frequency when adding a credit card.

## Solution Architecture

### Price Lookup Strategy
**Three-Tier Hybrid Approach:**
1. **Local djstripe cache** (1-5ms) - Check database first
2. **Stripe API lookup** (100-200ms) - Query with lookup_key
3. **Dynamic creation** (200-300ms) - Create new price if needed

### Key Components

#### 1. Pricing Service (`charj/cards/pricing_service.py`)
```python
def get_or_create_price(
    amount_cents: int,
    interval: str,  # 'day', 'week', 'month', 'year'
    interval_count: int = 1
) -> str
```
- Implements three-tier lookup
- Uses standardized lookup_key: `{interval}_{interval_count}_{amount_cents}`
- Returns Stripe Price ID

#### 2. Backend Changes

**Update `create_subscription_view` (charj/cards/views.py:139)**
- Accept new parameters: `amount`, `interval`, `interval_count`
- Validate inputs (min/max amounts, valid intervals)
- Call `get_or_create_price()` to get dynamic price ID
- Create subscription with dynamic price

**Add validation:**
- Minimum: $1 (100 cents)
- Maximum: $1000 (100000 cents)
- Valid intervals: day, week, month, year
- Valid interval_count: 1-36 for most intervals

#### 3. Frontend Changes

**Update `add_card.html`:**
- Add amount input field (number, min=$1, step=$0.01)
- Add billing frequency selector (dropdown or radio buttons)
- Add interval_count selector (for "every X months/weeks")
- Update pricing summary to show selected options dynamically
- Update JavaScript to send new fields in subscription request

**UI Options:**
- **Simple**: Just amount + 4 radio buttons (daily/weekly/monthly/yearly)
- **Advanced**: Amount + interval dropdown + interval_count input
- **Hybrid**: Presets + "Custom" option that reveals full controls

#### 4. Settings Configuration

**Add to `config/settings/base.py`:**
```python
# Stripe Product ID (reuse existing product)
STRIPE_PRODUCT_ID = env("STRIPE_PRODUCT_ID", default="")

# Pricing constraints
STRIPE_MIN_AMOUNT_CENTS = env.int("STRIPE_MIN_AMOUNT_CENTS", default=100)  # $1
STRIPE_MAX_AMOUNT_CENTS = env.int("STRIPE_MAX_AMOUNT_CENTS", default=100000)  # $1000
STRIPE_ALLOWED_INTERVALS = ['day', 'week', 'month', 'year']
STRIPE_MAX_INTERVAL_COUNT = env.int("STRIPE_MAX_INTERVAL_COUNT", default=36)
```

#### 5. Database/Model Changes

**Update `CardDisplay` dataclass (charj/cards/services.py:47):**
```python
@attrs.define
class CardDisplay:
    # ... existing fields ...
    subscription_amount_cents: int | None = None
    subscription_interval: str | None = None
    subscription_interval_count: int | None = None

    @property
    def subscription_amount_display(self) -> str:
        """Return formatted amount like '$5.00'"""
        if self.subscription_amount_cents:
            return f"${self.subscription_amount_cents / 100:.2f}"
        return None

    @property
    def subscription_frequency_display(self) -> str:
        """Return human-readable frequency like 'every 3 months'"""
        if not self.subscription_interval:
            return None
        count = self.subscription_interval_count or 1
        if count == 1:
            return f"{self.subscription_interval}ly"
        return f"every {count} {self.subscription_interval}s"
```

**Update `get_user_cards` function** to extract price details from subscription items.

#### 6. Testing Requirements

- Test all interval types (day, week, month, year)
- Test interval_count variations (1, 2, 3, 6, 12)
- Test various amounts ($1, $5.50, $99.99, $1000)
- Test price reuse (same combination twice)
- Test concurrent requests (race condition on price creation)
- Test validation (negative amounts, invalid intervals, etc.)
- Test edge cases (max amounts, max intervals)

## Implementation Steps

### Phase 1: Backend Core (Priority 1)
1. Create `pricing_service.py` with `get_or_create_price()`
2. Add settings configuration
3. Update `create_subscription_view` to accept new parameters
4. Add input validation
5. Write unit tests for pricing service

### Phase 2: Frontend (Priority 1)
1. Update `add_card.html` template with new form fields
2. Add dynamic pricing summary
3. Update JavaScript to send new parameters
4. Add client-side validation
5. Test user flow end-to-end

### Phase 3: Display Updates (Priority 2)
1. Update `CardDisplay` dataclass with price fields
2. Update `get_user_cards()` to extract price details
3. Update dashboard template to show subscription details
4. Test display on dashboard

### Phase 4: Polish (Priority 3)
1. Add UX improvements (presets, better formatting)
2. Add error messaging for validation failures
3. Add logging and monitoring
4. Update documentation

## Stripe Configuration Requirements

**Before implementation:**
1. Create or identify Stripe Product ID to reuse
2. Set `STRIPE_PRODUCT_ID` environment variable
3. Ensure webhook endpoint is configured (already done via djstripe)
4. Consider: Should we archive old unused prices? (Stripe allows this)

## Performance Considerations

**Expected performance:**
- **First request** for unique combination: ~300-400ms (Stripe API create)
- **Subsequent requests** for same combination: ~1-5ms (local DB lookup)
- **Price proliferation**: Unlimited combinations supported by Stripe
- **Database growth**: Minimal - Price table grows slowly (unique combinations only)

**Optimization opportunities:**
- Add database index on `lookup_key` field (djstripe likely already has this)
- Consider periodic cleanup of unused prices (Stripe dashboard or script)
- Cache common prices in Redis for sub-millisecond lookups (overkill for most cases)

## Rollout Strategy

**Option A: Feature Flag**
1. Implement behind feature flag
2. Test with internal users first
3. Gradually roll out to all users

**Option B: Parallel Deployment**
1. Keep existing $1/year flow as default
2. Add "Custom Pricing" option that reveals new interface
3. Monitor usage and iterate

**Option C: Full Replacement**
1. Replace existing flow entirely
2. Pre-populate with $1/year as default values
3. Users can modify before submitting

**Recommendation:** Option C with smart defaults ($1/year pre-filled) for smoothest transition.

## Open Questions

1. **UI/UX**: Simple (4 radio buttons) vs Advanced (interval_count input)?
2. **Defaults**: What should be pre-selected? ($1/year? $5/month?)
3. **Constraints**: Should we round to nearest dollar? (reduces price proliferation)
4. **Display**: Show all price combinations on dashboard, or just amount + frequency?
5. **Product**: Create new Stripe Product or reuse existing one? (Recommend: reuse)

## Success Metrics

- Price lookup cache hit rate > 95% (after warm-up)
- No duplicate prices created for same combination
- API response time < 500ms for price creation
- API response time < 100ms for price lookup
- Zero subscription creation failures due to pricing issues

## Resources

- [Stripe Price API Documentation](https://docs.stripe.com/api/prices/create)
- [djstripe Price Model Documentation](https://dj-stripe.dev/)
- [Stripe Billing Best Practices](https://stripe.dev/blog/optimizing-stripe-api-performance-lambda-caching-elasticache-dynamodb)
