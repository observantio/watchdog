import PropTypes from 'prop-types'
import { Spinner, Modal } from '../ui'
import RcaTabs from './RcaTabs'

/**
 * Modal wrapper used by the RCA page.  Parent provides all of the state and
 * the renderActiveTab callback.  This component simply handles the chrome
 * around the tabs and loading state.
 */
export default function RcaReportModal({
  isOpen,
  onClose,
  activeTab,
  setActiveTab,
  loadingPrimaryReport,
  loadingReport,
  hasReport,
  renderActiveTab,
  tabs,
}) {
  return (
    <div>
      <Modal
        isOpen={isOpen}
        onClose={onClose}
        title="Report Details"
        size="xl"
        className="p-0"
        closeOnOverlayClick={false}
      >
        {loadingPrimaryReport || loadingReport ? (
          <div className="p-6 text-sm flex items-center justify-center">
            <Spinner className="mr-3" /> Fetching the report... Powered By Be Certain
          </div>
        ) : hasReport ? (
          <>
            <RcaTabs
              tabs={tabs}
              activeTab={activeTab}
              onChange={setActiveTab}
              sticky
            />
            <div className="flex flex-col w-full space-y-3 px-0 py-4 [&_*]:not(button):!rounded-none [&_*]:not(button):!border-none [&_*]:not(button):!p-0">
              {renderActiveTab({ compact: true })}
            </div>
          </>
        ) : (
          <p className="text-sm text-sre-text-muted">
            Select a completed RCA job or look up a report ID to view report details.
          </p>
        )}
      </Modal>
    </div>
  )
}

RcaReportModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  activeTab: PropTypes.string.isRequired,
  setActiveTab: PropTypes.func.isRequired,
  loadingPrimaryReport: PropTypes.bool,
  loadingReport: PropTypes.bool,
  hasReport: PropTypes.bool,
  renderActiveTab: PropTypes.func.isRequired,
  tabs: PropTypes.array.isRequired,
}
