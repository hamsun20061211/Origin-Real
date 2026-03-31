using UnityEngine;

namespace OriginReal.Integration.Runtime
{
    /// <summary>
    /// 관절/바퀴 최소 예: 바퀴 Transform(또는 Rigidbody) 축 기준 토크.
    /// 정석 차량은 WheelCollider 4개 + 서스펜션 — 여기서는 프로토타입용.
    /// </summary>
    public sealed class SimpleWheelTorque : MonoBehaviour
    {
        [SerializeField] Rigidbody wheelBody;
        [SerializeField] Vector3 localAxis = Vector3.right;
        [SerializeField] float torque = 400f;

        void FixedUpdate()
        {
            if (wheelBody == null) return;
            Vector3 worldAxis = wheelBody.transform.TransformDirection(localAxis.normalized);
            wheelBody.AddTorque(worldAxis * torque, ForceMode.Force);
        }
    }
}
