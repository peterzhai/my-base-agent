/** 浏览器组合根：安装统一主题，再选择管理后台或宿主演示；不在入口中实现领域页面。 */
import { App, ConfigProvider } from "antd";
import { createRoot } from "react-dom/client";
import { DemoHost } from "./modules/host_demo";
import { Workbench } from "./modules/workbench";
import "./style.css";
createRoot(document.getElementById("root")!).render(
  <ConfigProvider
    theme={{
      token: {
        colorPrimary: "#176b62",
        borderRadius: 10,
        fontFamily:
          'Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif',
      },
    }}
  >
    <App>{location.pathname === "/demo" ? <DemoHost /> : <Workbench />}</App>
  </ConfigProvider>,
);
