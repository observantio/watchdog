import PropTypes from 'prop-types'
import { Button } from '../ui'

export default function RuleEditorWizard({ currentStep, totalSteps, onNext, onPrevious, onSubmit, canProceed, isSubmitting, hasErrors, showIndicator = true, showButtons = true, steps: customSteps }) {
  const defaultSteps = [
    { key: 'basic', label: 'Basic Setup', icon: 'settings', description: 'Name, severity & product' },
    { key: 'condition', label: 'Alert Condition', icon: 'functions', description: 'Expression & timing' },
    { key: 'details', label: 'Alert Details', icon: 'description', description: 'Summary & labels' },
    { key: 'advanced', label: 'Advanced Settings', icon: 'tune', description: 'Channels & visibility' },
  ]
  const steps = Array.isArray(customSteps) && customSteps.length > 0 ? customSteps : defaultSteps

  const isLastStep = currentStep === totalSteps - 1
  const isFirstStep = currentStep === 0

  return (
    <div className="space-y-6">
      {/* Progress Indicator */}
      {showIndicator && (
        <div className="flex items-center justify-between">
          {steps.map((step, index) => {
            const isActive = index === currentStep
            const isCompleted = index < currentStep
            const isUpcoming = index > currentStep

            return (
              <div key={step.key} className="flex flex-col items-center flex-1 min-w-0">
                <div className="flex flex-col items-center">
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium transition-all duration-300 ${
                      isCompleted
                        ? 'bg-sre-success text-white shadow-lg'
                        : isActive
                        ? 'bg-sre-primary text-white shadow-lg ring-4 ring-sre-primary/20'
                        : 'bg-sre-surface border-2 border-sre-border text-sre-text-muted'
                    }`}
                  >
                    {isCompleted ? (
                      <span className="material-icons text-lg">check</span>
                    ) : (
                      <span className="material-icons text-base">{step.icon}</span>
                    )}
                  </div>
                  <div className="mt-2 text-center min-w-0 flex-1">
                    <div className={`text-xs font-medium ${isActive ? 'text-sre-primary' : isCompleted ? 'text-sre-success' : 'text-sre-text-muted'}`}>
                      {step.label}
                    </div>
                    <div className={`text-[10px] text-sre-text-muted mt-0.5 leading-tight ${isActive ? 'text-sre-primary/70' : ''}`}>
                      {step.description}
                    </div>
                  </div>
                </div>
                {index < steps.length - 1 && (
                  <div
                    className={`flex-1 h-0.5 mx-4 transition-colors duration-300 ${
                      isCompleted ? 'bg-sre-success' : 'bg-sre-border'
                    }`}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Navigation Buttons */}
      {showButtons && (
        <div className="flex justify-between items-center  border-sre-border">
          <Button
            type="button"
            variant="ghost"
            onClick={onPrevious}
            disabled={isFirstStep}
            className="flex items-center gap-2"
          >
            <span className="material-icons text-sm">arrow_back</span>
            Previous
          </Button>

          <div className="text-sm text-sre-text-muted">
            Step {currentStep + 1} of {totalSteps}
          </div>

          {isLastStep ? (
            <Button
              type="button"
              variant="primary"
              onClick={onSubmit}
              disabled={!canProceed || hasErrors || isSubmitting}
              className="flex items-center gap-2 bg-gradient-to-r from-sre-primary to-sre-primary-light hover:from-sre-primary-light hover:to-sre-primary shadow-lg"
            >
              {isSubmitting ? (
                <>
                  <span className="material-icons text-sm animate-spin">refresh</span>
                  Creating Rule...
                </>
              ) : (
                <>
                  <span className="material-icons text-sm">check_circle</span>
                  Create Rule
                </>
              )}
            </Button>
          ) : (
            <Button
              type="button"
              variant="primary"
              onClick={onNext}
              disabled={!canProceed}
              className="flex items-center gap-2"
            >
              Next
              <span className="material-icons text-sm">arrow_forward</span>
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

RuleEditorWizard.propTypes = {
  currentStep: PropTypes.number.isRequired,
  totalSteps: PropTypes.number.isRequired,
  onNext: PropTypes.func.isRequired,
  onPrevious: PropTypes.func.isRequired,
  onSubmit: PropTypes.func.isRequired,
  canProceed: PropTypes.bool.isRequired,
  isSubmitting: PropTypes.bool,
  hasErrors: PropTypes.bool.isRequired,
  showIndicator: PropTypes.bool,
  showButtons: PropTypes.bool,
  steps: PropTypes.array,
}