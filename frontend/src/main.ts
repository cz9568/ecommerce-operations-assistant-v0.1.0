import { createApp } from "vue"

import App from "./App.vue"
import { AUTH_UNAUTHORIZED_EVENT } from "./api/http"
import router from "./router"
import { pinia } from "./stores"
import { useAuthStore } from "./stores/auth"
import "./style.css"

const app = createApp(App)
app.use(pinia)
app.use(router)

const authStore = useAuthStore(pinia)
window.addEventListener(AUTH_UNAUTHORIZED_EVENT, () => {
  authStore.clearSession()
  if (router.currentRoute.value.name !== "login") {
    void router.replace({
      name: "login",
      query: { reason: "expired", redirect: router.currentRoute.value.fullPath },
    })
  }
})

app.mount("#app")
