import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles.css'
import Root from './Root.vue'
import router from './router'

createApp(Root).use(ElementPlus).use(router).mount('#app')
