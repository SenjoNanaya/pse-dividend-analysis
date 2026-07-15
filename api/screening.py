"""Live checklist rescoring helpers for the company list API."""
from django.db.models import Case, F, IntegerField, Value, When

from src.report_metrics import DEFAULT_THRESHOLDS, normalize_thresholds


def thresholds_from_request(request):
    """Parse pe_max / pb_max / roe_min from query params (defaults when absent)."""
    raw = {}
    for key in ("pe_max", "pb_max", "roe_min"):
        val = request.query_params.get(key)
        if val is None or val == "":
            continue
        try:
            raw[key] = float(val)
        except (TypeError, ValueError):
            continue
    return normalize_thresholds(raw)


def annotate_live_checks(queryset, thresholds=None):
    """
    Annotate live_check_pass / live_check_eval using stored structural counts
    plus PE/PB/ROE from company columns vs request thresholds.
    """
    t = normalize_thresholds(thresholds)
    pe_max = t["pe_max"]
    pb_max = t["pb_max"]
    roe_min = t["roe_min"]

    # Usable scraped ratios: non-null and |value| <= 1000
    pe_eval = Case(
        When(pe_ratio__isnull=False, pe_ratio__gte=-1000, pe_ratio__lte=1000, then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )
    pe_pass = Case(
        When(
            pe_ratio__isnull=False,
            pe_ratio__gte=-1000,
            pe_ratio__lte=1000,
            pe_ratio__lt=pe_max,
            then=Value(1),
        ),
        default=Value(0),
        output_field=IntegerField(),
    )
    pb_eval = Case(
        When(pb_ratio__isnull=False, pb_ratio__gte=-1000, pb_ratio__lte=1000, then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )
    pb_pass = Case(
        When(
            pb_ratio__isnull=False,
            pb_ratio__gte=-1000,
            pb_ratio__lte=1000,
            pb_ratio__lt=pb_max,
            then=Value(1),
        ),
        default=Value(0),
        output_field=IntegerField(),
    )
    roe_eval = Case(
        When(roe__isnull=False, then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )
    roe_pass = Case(
        When(roe__isnull=False, roe__gt=roe_min, then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )

    struct_pass = Case(
        When(check_struct_pass__isnull=False, then=F("check_struct_pass")),
        default=Value(0),
        output_field=IntegerField(),
    )
    struct_eval = Case(
        When(check_struct_eval__isnull=False, then=F("check_struct_eval")),
        default=Value(0),
        output_field=IntegerField(),
    )

    return queryset.annotate(
        live_check_pass=struct_pass + pe_pass + pb_pass + roe_pass,
        live_check_eval=struct_eval + pe_eval + pb_eval + roe_eval,
    )


def default_thresholds():
    return dict(DEFAULT_THRESHOLDS)
