/** 运行治理页面：定时刷新任务和审计，组件卸载时必须清除计时器。 */
import { ReloadOutlined } from "@ant-design/icons";
import { AgentClient } from "@factory-agent/chat";
import { Button, Table, message } from "antd";
import { useCallback, useEffect, useState } from "react";

export function Logs({ kind, client }: { kind: string; client: AgentClient }) {
  const [rows, setRows] = useState<any[]>([]);
  const refresh = useCallback(async () => {
    try {
      setRows(await client.json(`/admin/${kind}`));
    } catch (e) {
      message.error(String(e));
    }
  }, [kind, client]);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh]);
  const columns =
    kind === "jobs"
      ? [
          { title: "任务", dataIndex: "kind" },
          { title: "状态", dataIndex: "status" },
          {
            title: "进度",
            dataIndex: "progress",
            render: (v: number) => `${v}%`,
          },
          { title: "尝试次数", dataIndex: "attempts" },
          { title: "错误", dataIndex: "error" },
          {
            title: "操作",
            render: (_: unknown, r: any) => (
              <Button
                disabled={r.status !== "failed"}
                onClick={async () => {
                  await client.json(`/admin/jobs/${r.id}/retry`, {
                    method: "POST",
                  });
                  await refresh();
                }}
              >
                重试
              </Button>
            ),
          },
        ]
      : [
          { title: "时间", dataIndex: "created_at" },
          { title: "用户", dataIndex: "user_id" },
          { title: "操作", dataIndex: "action" },
          { title: "资源", dataIndex: "resource" },
        ];
  return (
    <>
      <div className="section-actions">
        <span>每 5 秒刷新 · 最近记录</span>
        <Button icon={<ReloadOutlined />} onClick={refresh}>
          刷新
        </Button>
      </div>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={columns}
        expandable={{
          expandedRowRender: (r) => (
            <pre className="json-preview">
              {JSON.stringify(r.details ?? r.payload, null, 2)}
            </pre>
          ),
        }}
      />
    </>
  );
}
