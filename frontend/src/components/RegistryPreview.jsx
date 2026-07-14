import ChecklistPreview from './ChecklistPreview';
import { buildReport } from '../lib/metrics';

export default function RegistryPreview({ company, status, onOpen, onClear }) {
  if (status === 'loading') {
    return (
      <div className="nier-outer-box h-full">
        <div className="nier-inner-box p-4">
          <p className="text-xs uppercase tracking-widest opacity-60 py-8 text-center">
            LOADING_RECORD_PREVIEW...
          </p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="nier-outer-box h-full">
        <div className="nier-inner-box p-4">
          <p className="text-xs uppercase tracking-widest text-nier-orange py-8 text-center">
            PREVIEW_RETRIEVAL_FAILURE
          </p>
        </div>
      </div>
    );
  }

  if (!company) {
    return (
      <div className="nier-outer-box h-full">
        <div className="nier-inner-box p-4 flex flex-col justify-center items-center text-center min-h-48">
          <p className="text-[10px] uppercase tracking-widest font-bold opacity-50 mb-2">
            RECORD_PREVIEW_UNIT
          </p>
          <p className="text-xs uppercase tracking-widest opacity-60">
            Select a company row to preview screening checklist and ratios.
          </p>
        </div>
      </div>
    );
  }

  const report = buildReport(company);

  return (
    <div className="nier-outer-box h-full">
      <div className="nier-inner-box p-4 flex flex-col gap-4">
        <div className="flex justify-between items-start gap-2 border-b border-nier-dark/30 pb-3">
          <div className="min-w-0">
            <div className="text-2xl font-extrabold text-nier-orange tracking-wide">
              {report.displayTicker}
            </div>
            <div className="text-[10px] uppercase tracking-wider opacity-75 mt-1 leading-snug">
              {report.companyName}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-[10px] uppercase tracking-widest font-bold opacity-60">
              Market Cap
            </div>
            <div className="text-lg font-extrabold">{report.marketCapLabel}</div>
          </div>
        </div>

        <div>
          <div className="nier-data-block-title">Screening Preview</div>
          <ChecklistPreview report={report} compact showRatios />
        </div>

        <div className="flex gap-2 mt-auto pt-2">
          <button type="button" className="nier-btn grow text-xs" onClick={() => onOpen(company.id)}>
            OPEN FULL RECORD
          </button>
          {onClear && (
            <button type="button" className="nier-btn px-3 text-xs" onClick={onClear}>
              CLEAR
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
