using UnityEngine;

namespace OriginReal.Integration.Runtime
{
    /// <summary>단일 메쉬 루트: 전방으로 힘 적용. MeshCollider(convex) 또는 BoxCollider 권장.</summary>
    [RequireComponent(typeof(Rigidbody))]
    public sealed class RollForward : MonoBehaviour
    {
        [SerializeField] float force = 25f;

        Rigidbody _rb;

        void Awake()
        {
            _rb = GetComponent<Rigidbody>();
            _rb.interpolation = RigidbodyInterpolation.Interpolate;
        }

        void FixedUpdate()
        {
            _rb.AddForce(transform.forward * force, ForceMode.Force);
        }
    }
}
