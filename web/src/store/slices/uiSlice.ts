import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

interface UiState {
  sidebarOpen: boolean
  activeModal: string | null
  selectedAgentName: string | null
}

const initialState: UiState = {
  sidebarOpen: false,
  activeModal: null,
  selectedAgentName: null,
}

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    toggleSidebar: (state) => {
      state.sidebarOpen = !state.sidebarOpen
    },
    openModal: (state, action: PayloadAction<string>) => {
      state.activeModal = action.payload
    },
    closeModal: (state) => {
      state.activeModal = null
    },
    selectAgent: (state, action: PayloadAction<string | null>) => {
      state.selectedAgentName = action.payload
    },
  },
})

export const { toggleSidebar, openModal, closeModal, selectAgent } = uiSlice.actions
export default uiSlice.reducer
