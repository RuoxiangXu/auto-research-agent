import { createApp } from "vue";
import { marked } from "marked";
import App from "./App.vue";
import { createRouter, createWebHistory } from "vue-router";

marked.use({ breaks: true });

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
