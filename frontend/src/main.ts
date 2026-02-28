import { createApp } from "vue";
import App from "./App.vue";
import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: () => import("./views/Research.vue"),
    },
    {
      path: "/history",
      component: () => import("./views/History.vue"),
    },
  ],
});

const app = createApp(App);
app.use(router);
app.mount("#app");
