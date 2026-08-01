import { createContext, useContext } from 'react';


const EMPTY_QUEUE = Object.freeze({ activeCount: 0, groups: [] });
const EMPTY_FAILURES = Object.freeze({ failureCount: 0, items: [] });


export const AppFrameOperationsContext = createContext({
  jobQueue: EMPTY_QUEUE,
  failureNotifications: EMPTY_FAILURES,
  jobQueueOpen: false,
  failureNotificationsOpen: false,
  openJobQueue: () => {},
  openFailureNotifications: () => {}
});


export function useAppFrameOperations() {
  return useContext(AppFrameOperationsContext);
}
