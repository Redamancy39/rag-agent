import { createApp } from 'vue'
import { ElLoading } from 'element-plus'
import 'element-plus/es/components/base/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/loading/style/css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/layout.css'
import Root from './Root.vue'
import router from './router'

const app = createApp(Root)
app.use(ElLoading)
app.use(router)
app.mount('#app')
