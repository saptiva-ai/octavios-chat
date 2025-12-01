/**
 * BankChartError - Error state for bank chart
 *
 * Displays error message with retry option.
 */

import {
  ExclamationTriangleIcon,
  ArrowPathIcon,
} from "@heroicons/react/24/outline";

interface BankChartErrorProps {
  message?: string;
  onRetry?: () => void;
  showRetry?: boolean;
}

export function BankChartError({
  message = "No se pudo cargar la gráfica. Por favor, intenta nuevamente.",
  onRetry,
  showRetry = true,
}: BankChartErrorProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center p-8 text-center">
      <div className="rounded-full bg-red-500/10 p-4 mb-4">
        <ExclamationTriangleIcon className="h-16 w-16 text-red-400" />
      </div>

      <h3 className="text-lg font-semibold text-white mb-2">
        Error al cargar la gráfica
      </h3>

      <p className="text-sm text-white/60 mb-6 max-w-md">{message}</p>

      {showRetry && onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-4 py-2 text-sm font-medium text-primary hover:border-primary/50 hover:bg-primary/20 transition-colors"
        >
          <ArrowPathIcon className="h-4 w-4" />
          Reintentar
        </button>
      )}

      <div className="mt-8 text-xs text-white/40">
        Si el problema persiste, contacta al administrador.
      </div>
    </div>
  );
}
